"""
Spectrogram rendering, organised around *events* rather than whole recordings.

This module replaces the two standalone spectrogram scripts:

  make-spectrogram-movie-fixed.sh      -> render_clip_video() / whole_file_video()
  make-spectrogram-thumbnail-fixed.sh  -> render_clip_poster()

The important change is the unit of work. The old scripts rendered one
spectrogram per recording, which buries a 12-second amphibian assembly inside
an hour of tape. Here every detected event becomes its own short clip with its
own video, colour-coded by acoustic domain, labelled with its ecological role,
and optionally concatenated into one reel per event type.
"""

import math
from dataclasses import dataclass, field
from pathlib import Path

from .config import ClipConfig, VideoConfig
from .classifier import certainty_of
from .media import (OverlayTexts, TextOverlay, can_draw_text, concat_videos,
                    find_font, have_ffmpeg, run_ffmpeg, video_to_gif)

# ffmpeg's showspectrum fscale=log is logarithmic in (f - start) above a fixed
# 20 Hz floor:
#
#     y = ln((f - start) / 20) / ln((stop - start) / 20)      y=0 at the bottom
#
# This is measured, not documented: pure tones were rendered at known
# frequencies and their pixel rows read back, and the curve was confirmed
# against the tick values ffmpeg prints in its own legend. It matters because
# the shape is far more aggressive than a plain log — with start=2000 and
# stop=56568, the bottom half of the frame covers only 2000-3043 Hz. That, not
# the colormap, is what made the low end of the plot look like a wash.
LOG_FLOOR_HZ = 20.0

# Rendering taller than the frame to get a true log axis (see log_axis) costs
# FFT work proportional to the height. Narrow windows want enormous heights, so
# the ratio is capped and the visible floor moves instead of the labels lying.
MAX_RENDER_HEIGHT = 3072

# Advance width of a monospaced glyph as a fraction of its point size. Used to
# work out how many characters fit across the ticker; Monaco and the other
# fallbacks are all close to 0.6 em.
MONO_ADVANCE = 0.6

# Distance between baselines as a multiple of the point size, before
# line_spacing is added. drawtext uses the font's own line height, which is
# taller than the point size — assuming they were equal left the last line of
# the ticker hanging off the bottom of the frame.
MONO_LINE_HEIGHT = 1.4


def _smooth_height(h: int, limit: int = 8192) -> int:
    """
    Round a render height up until its FFT size is a cheap one.

    showspectrum uses a transform of twice the plot height, and hits a slow
    path when that size has large prime factors. The difference is not
    marginal: height 1517 (2 x 37 x 41) took 16 s of CPU for two seconds of
    audio, while 1512 and 1536 either side of it took 0.3 s — a 50x cliff for a
    1% change in height. Snapping to numbers of the form 2^a x 3^b x 5^c keeps
    every render on the fast path.
    """
    best = limit
    p2 = 1
    while p2 <= limit:
        p23 = p2
        while p23 <= limit:
            n = p23
            while n <= limit:
                if h <= n < best:
                    best = n
                n *= 5
            p23 *= 3
        p2 *= 2
    return best


# How long an FFT window should cover, in seconds. showspectrum ties its
# window to the plot height, so a tall render on a 48 kHz file would otherwise
# smear 90 ms of audio into one column and blur every syllable.
TARGET_WINDOW_S = 0.025


def spectrum_feed(source_rate: int, render_h: int,
                  target_window_s: float = TARGET_WINDOW_S) -> int:
    """
    Rate to feed the spectrogram at, or 0 to leave the stream alone.

    The window length in samples is fixed by the render height, so the only way
    to choose how much *time* it covers is to choose the sample rate. Feeding a
    48 kHz file at a higher rate shortens the window in time and lengthens it in
    frequency — the ordinary time/frequency trade, made deliberately instead of
    inherited from whatever the recorder happened to be set to.

    Never downsamples: that would lengthen the window and blur time further.
    """
    if not source_rate:
        return 0
    wanted = int(2 * render_h / target_window_s)
    return wanted if wanted > source_rate else 0


def spectrum_overlap(source_rate: int, render_h: int,
                     target_columns_per_s: int = 300) -> float:
    """
    Window overlap that makes the spectrogram scroll in at a watchable rate.

    showspectrum emits one column per FFT hop, so the time it takes to fill the
    frame is width / (rate / hop). The taller renders this module asks for mean
    a longer hop, and without overlap a 20-second clip would still be half
    empty when it ended. Overlapping the windows decouples how fast the picture
    fills from how tall it is.
    """
    if not source_rate or render_h <= 0:
        return 0.0
    hop_fraction = source_rate / (target_columns_per_s * 2 * render_h)
    return round(min(0.9, max(0.0, 1.0 - hop_fraction)), 3)


@dataclass
class ClipRender:
    """Files produced for one event clip."""
    video: str = ""
    poster: str = ""
    thumbnail: str = ""
    gif: str = ""
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "video_path": self.video,
            "poster_path": self.poster,
            "thumbnail_path": self.thumbnail,
            "gif_path": self.gif,
        }


def freq_window(event: dict, config: VideoConfig) -> tuple[int, int]:
    """
    Frequency range to plot for one event.

    Without focus this is simply [min_freq, max_freq]. With it, the plot is
    bracketed around the band the event actually occupies, widened by
    `focus_margin_octaves` on each side so neighbouring activity stays visible.
    The floor never drops below min_freq: on a log axis the sub-200 Hz rumble
    would otherwise take a third of the height and show nothing.
    """
    lo, hi = config.min_freq, config.max_freq
    if not config.focus_on_event:
        return lo, hi

    band_lo = event.get("band_lo_hz")
    band_hi = event.get("band_hi_hz")
    if not band_hi:
        return lo, hi

    focus_lo = max(lo, int((band_lo or 0) / 2.0 ** config.focus_margin_octaves_down))
    focus_hi = min(hi, int(band_hi * 2.0 ** config.focus_margin_octaves_up))
    if focus_hi <= focus_lo:
        return lo, hi
    return focus_lo, focus_hi


def log_axis(f_lo: float, f_hi: float, plot_h: int, min_height: int = 0,
             max_height: int = MAX_RENDER_HEIGHT) -> tuple[int, float]:
    """
    Render height that puts [f_lo, f_hi] across the top `plot_h` rows, log-spaced.

    Returns `(render_height, visible_f_lo)`.

    With `start=0` ffmpeg's curve collapses to a plain logarithm of frequency,
    from the 20 Hz floor up to `stop`. Everything below `f_lo` is then a fixed
    fraction of that taller plot, so rendering tall and keeping the top leaves
    exactly [f_lo, f_hi] spread evenly by octave — which is what a spectrogram
    is supposed to look like, and what passing `start=f_lo` does not give.

    `plot_h` is the part of the frame that stays uncovered by the ticker;
    `min_height` is the whole frame, since the crop still has to fill it. Rows
    between the two show frequencies below `f_lo`, hidden behind the ticker.

    When the requested band is narrow the required height runs away (an octave
    inside a 20 Hz-to-56 kHz plot is a sliver), so it is capped. The visible
    floor then rises above `f_lo`; that is returned so the axis labels describe
    the picture actually rendered rather than the one that was asked for.
    """
    height = max(plot_h, min_height)
    if f_hi <= f_lo or f_lo <= LOG_FLOOR_HZ:
        return height, max(f_lo, LOG_FLOOR_HZ)

    decades = math.log(f_hi / LOG_FLOOR_HZ)
    visible = math.log(f_hi / f_lo) / decades
    render_h = max(height, int(round(plot_h / visible)))

    if render_h > max_height:
        render_h = max(height, max_height)
    render_h = _smooth_height(render_h)
    # Whatever height survived the clamps, report the frequency that actually
    # lands at the bottom of the uncovered region.
    f_lo = f_hi * math.exp(-(plot_h / render_h) * decades)
    return render_h, f_lo


# Round numbers to label an axis with, coarsening as the span grows.
_TICK_TIERS = ((1, 1.5, 2, 3, 5, 7), (1, 2, 3, 5), (1, 2, 5), (1, 3), (1,))


def freq_ticks(f_lo: float, f_hi: float,
               max_ticks: int = 9) -> list[tuple[float, float]]:
    """Round frequencies to label, each with its height fraction (0 = bottom)."""
    if f_hi <= f_lo:
        return []
    span = math.log(f_hi / f_lo)
    chosen: list[float] = []
    for tier in _TICK_TIERS:
        chosen = []
        decade = math.floor(math.log10(f_lo))
        while 10 ** decade <= f_hi:
            for mantissa in tier:
                f = mantissa * 10 ** decade
                if f_lo <= f <= f_hi:
                    chosen.append(f)
            decade += 1
        if len(chosen) <= max_ticks:
            break
    return [(f, math.log(f / f_lo) / span) for f in chosen[:max_ticks]]


def tick_label(f: float) -> str:
    """Axis label for a frequency, in the shortest form that stays unambiguous."""
    if f >= 10000:
        return f"{f / 1000:.0f}K"
    if f >= 1000:
        return f"{f / 1000:.1f}K"
    return f"{f:.0f}"


def _spectrum_filter(config: VideoConfig, color: str,
                     window: tuple[int, int] | None = None,
                     axis: tuple[int, float] | None = None) -> str:
    """The showspectrum source filter, shared by clip and whole-file renders."""
    start, stop = window or (config.min_freq, config.max_freq)

    if config.freq_scale == "log" and axis is not None:
        render_h, _ = axis
        feed = spectrum_feed(config.source_rate, render_h)
        overlap = spectrum_overlap(feed or config.source_rate, render_h)
        chain = (
            f"[0:a]{f'aresample={feed},' if feed else ''}showspectrum="
            f"s={config.width}x{render_h}:"
            f"legend=disable:"
            f"start=0:"
            f"stop={stop}:"
            f"fscale=log:"
            f"color={color}:"
            f"drange={config.dynamic_range}:"
            f"scale={config.gain_scale}:"
            f"overlap={overlap}:"
            f"slide={config.slide}"
        )
        if render_h != config.height:
            chain += f",crop={config.width}:{config.height}:0:0"
        return chain + f",fps={config.video_fps}"

    return (
        f"[0:a]showspectrum="
        f"s={config.width}x{config.height}:"
        f"legend={config.legend}:"
        f"start={start}:"
        f"stop={stop}:"
        f"fscale={config.freq_scale}:"
        f"color={color}:"
        f"drange={config.dynamic_range}:"
        f"scale={config.gain_scale}:"
        f"slide={config.slide}"
        f",fps={config.video_fps}"
    )


def _encode_args(config: VideoConfig, output_path: str) -> list[str]:
    return [
        "-map", "[v]", "-map", "0:a",
        "-c:v", config.video_codec,
        "-preset", config.video_preset,
        "-crf", str(config.video_crf),
        "-c:a", config.audio_codec,
        "-b:a", config.audio_bitrate,
        "-movflags", "+faststart",
        "-y", output_path,
    ]


def _render_spectrogram_video(wav_path: str, output_path: str,
                              overlays: list[TextOverlay],
                              color: str,
                              config: VideoConfig,
                              window: tuple[int, int] | None = None,
                              axis: tuple[int, float] | None = None,
                              boxes: list[str] | None = None) -> tuple[bool, str]:
    """
    Render a scrolling spectrogram video with the given text overlays.

    Overlays are dropped when the ffmpeg build has no drawtext filter (it needs
    libfreetype, which Homebrew's stock bottle omits). The spectrogram and the
    audio are unaffected — only the burned-in text is lost, and the same
    information stays in the filename, the gallery card, the report and
    events.json. With the legend disabled that also costs the frequency axis,
    so the note printed when drawtext is missing says as much.
    """
    draw_text = config.overlay_text and can_draw_text()

    with OverlayTexts(config.font_file) as texts:
        chain = _spectrum_filter(config, color, window, axis)
        for box in boxes or []:
            chain += "," + box
        if draw_text:
            for overlay in overlays:
                if overlay.text:
                    chain += "," + texts.filter_for(overlay)
        chain += ",format=yuv420p[v]"

        return run_ffmpeg(["-i", wav_path, "-filter_complex", chain,
                           *_encode_args(config, output_path)])


FIELD_SEP = " · "


def _fold(text: str, width: int, indent: str = "    ") -> list[str]:
    """Break one long field list across lines without cutting mid-word."""
    if len(text) <= width:
        return [text]
    out, rest = [], text
    while len(rest) > width:
        cut = rest.rfind(" ", 0, width)
        if cut <= len(indent):
            cut = width
        out.append(rest[:cut].rstrip())
        rest = indent + rest[cut:].lstrip()
    out.append(rest)
    return out


def ticker_lines(event: dict, recording_meta: dict, window: tuple[float, float],
                 config: VideoConfig, width_chars: int) -> list[str]:
    """
    Everything known about the clip, as a few full-width lines.

    This replaces the right-hand metadata column. A column forces every value
    onto its own row, which is why it needed thirty of them and still wrapped
    land-cover names; laid out along the frame the same content fits in four.

    The grouping still separates what was measured from what was inferred: the
    VOICES line is the only claim the toolkit makes, and it carries its own
    certainty. Everything else is a survey fact, a recorder fact, or a number
    computed from the audio.
    """
    dt = recording_meta.get("datetime")
    sr = recording_meta.get("samplerate_hz") or 0
    temp = recording_meta.get("temperature_c")
    lat, lon = event.get("latitude"), event.get("longitude")
    f_lo, f_hi = window

    def row(label: str, parts: list[str]) -> str:
        kept = [p for p in parts if p]
        return f"{label} {FIELD_SEP.join(kept)}" if kept else ""

    # Where and when, survey facts and recorder facts together: both answer
    # "which recording is this", and split across two rows they left the
    # measurements no room.
    site = row("SITE", [
        str(recording_meta.get("habitat") or ""),
        str(event.get("locality") or ""),
        str(event.get("station_id") or ""),
        (f"{lat:.5f} {lon:.5f}" if lat is not None and lon is not None else ""),
        (f"{event['elevation_m']:.0f} m"
         if event.get("elevation_m") is not None else ""),
        str(recording_meta.get("season") or ""),
        (dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""),
        str(recording_meta.get("audiomoth_id") or ""),
        (f"{temp:.1f} C" if temp is not None else ""),
        (f"{sr / 1000:.0f} kHz" if sr else ""),
        (f"{recording_meta['battery_v']:.2f} V"
         if recording_meta.get("battery_v") is not None else ""),
    ])

    # The only line that carries a claim rather than a reading.
    voices = row("VOX ", [
        _inferred_label(event),
        f"onset {event.get('onset_s', 0):.2f} s",
        f"length {event.get('duration_s', 0):.2f} s",
    ])

    shares = event.get("band_shares") or {}
    measured = row("MEAS", [
        *(f"{name.replace('_', ' ')} {share:.0%}"
          for name, share in shares.items()),
        f"centroid {event.get('centroid', 0) / 1000:.2f} kHz",
        (f"in-band {event.get('band_centroid', 0) / 1000:.2f} kHz"
         if event.get("band_centroid") else ""),
        (f"crest {event.get('band_crest', 0):.1f}"
         if event.get("band_crest") else ""),
        (f"entropy {event.get('band_entropy', 0):.3f}"
         if event.get("band_entropy") else ""),
        (f"pulse {event['pulse_rate_hz']:.1f} Hz"
         if event.get("periodicity", 0) >= 0.2
         and event.get("pulse_rate_hz") else ""),
    ])

    indices = row("IDX ", [
        f"ACI {event.get('aci', 0):.1f}",
        f"BIO {event.get('bio', 0):.1f}",
        f"NDSI {event.get('ndsi', 0):+.3f}",
        f"ADI {event.get('adi', 0):.3f}",
        f"AEI {event.get('aei', 0):.3f}",
        f"view {tick_label(f_lo)}-{tick_label(f_hi)}",
        f"-{config.dynamic_range}..0 dBFS",
    ])

    lines: list[str] = []
    for text in (site, voices, measured, indices):
        if text:
            lines.extend(_fold(text, width_chars))
    return lines


def _inferred_label(event: dict) -> str:
    """
    Every voice the event carries, and how far the naming can be trusted.

    An earlier version printed only "unclassified", which told a viewer nothing
    about what they were looking at. The qualifier stays because the rules are
    uncalibrated, and naming after the plurality alone is what made a pond full
    of frogs read as insects.
    """
    confidence = event.get("confidence", 0.0)
    certainty = event.get("certainty") or certainty_of(confidence)
    qualifier = {"probable": "probable",
                 "candidate": "candidate",
                 "unclassified": "unverified"}.get(certainty, certainty)
    names = event.get("roles") or [event.get("role", "event")]
    inferred = " + ".join(n.replace("_", " ") for n in names)
    return f"{inferred} [{qualifier} {confidence:.0%}]"


def render_clip_video(clip_path: str, output_path: str, event: dict,
                      recording_meta: dict,
                      config: VideoConfig | None = None) -> tuple[bool, str]:
    """
    Render one event clip as a spectrogram video.

    Every glyph on the frame is drawn here, at one size in one face. ffmpeg's
    own legend is disabled: it writes its axis labels with a bitmap font
    compiled into libavfilter, which cannot be loaded as a file, so keeping it
    meant permanently mixing two typefaces. Drawing the frequency axis by hand
    is possible because `log_axis` pins down exactly where each frequency lands.

    Layout: site and running clock along the top, frequency axis down the left,
    and a full-width ticker of everything known about the clip along the bottom.
    """
    config = config or VideoConfig()
    domain = event.get("domain", "")
    up = (lambda s: s.upper()) if config.uppercase else (lambda s: s)

    f_lo, f_hi = freq_window(event, config)

    # The ticker is sized from its own content, so a clip with no GIS layer
    # gets a shorter band rather than a reserved empty one. Its height has to
    # be known before the axis, because the ticker covers the bottom of the
    # frame: the band that must span [f_lo, f_hi] is what stays visible above
    # it, not the whole picture.
    #
    # The two depend on each other — the ticker names the frequency range, and
    # the range depends on how much room the ticker leaves — so settle them by
    # iterating. Two passes is always enough in practice; the loop just makes
    # sure the height used to place the labels is the height that was drawn.
    char_w = config.ticker_font_size * MONO_ADVANCE
    width_chars = max(20, int((config.width - 2 * config.ticker_pad_px) / char_w))
    line_h = (round(config.ticker_font_size * MONO_LINE_HEIGHT)
              + config.ticker_line_spacing)
    visible_lo, lines, ticker_h, plot_h, axis = f_lo, [], 0, config.height, None
    for _ in range(4):
        lines = (ticker_lines(event, recording_meta, (visible_lo, f_hi),
                              config, width_chars) if config.show_ticker else [])
        new_h = len(lines) * line_h + config.ticker_pad_px if lines else 0
        plot_h = max(64, config.height - new_h)
        axis = log_axis(f_lo, f_hi, plot_h, min_height=config.height)
        new_lo = axis[1] if config.freq_scale == "log" else f_lo
        if new_h == ticker_h and abs(new_lo - visible_lo) < 1.0:
            ticker_h = new_h
            break
        ticker_h, visible_lo = new_h, new_lo

    boxes = ([f"drawbox=x=0:y=ih-{ticker_h}:w=iw:h={ticker_h}:"
              f"color=black@{config.ticker_opacity}:t=fill"] if ticker_h else [])

    # No site header along the top any more: it repeats the ticker's SITE line
    # and it sat exactly where the highest frequency label needs to go.
    overlays = [
        # Restores the elapsed-time reading that showspectrum's TIME axis used
        # to give. The only overlay that needs drawtext expansion.
        TextOverlay(
            # No backslash before the colon: that escape is for filter-argument
            # parsing, and inside a textfile it stops the expansion matching.
            text="T +%{eif:t:d}s",
            x=f"W-tw-{config.ticker_pad_px}", y=str(config.ticker_pad_px),
            font_size=config.date_font_size, expansion="normal",
        ),
    ]

    for freq, frac in freq_ticks(visible_lo, f_hi):
        # drawtext anchors at the top of the glyph; shift up by half a line so
        # the label sits centred on the frequency it names.
        row = (1.0 - frac) * plot_h
        y = max(2, min(plot_h - config.tick_font_size,
                       int(round(row - config.tick_font_size / 2))))
        overlays.append(TextOverlay(
            text=up(f"{tick_label(freq):>5}"),
            x=str(config.ticker_pad_px), y=str(y),
            font_size=config.tick_font_size,
        ))

    if lines:
        overlays.append(TextOverlay(
            text=up("\n".join(lines)),
            x=str(config.ticker_pad_px),
            y=str(config.height - ticker_h + config.ticker_pad_px // 2),
            font_size=config.ticker_font_size,
            line_spacing=config.ticker_line_spacing,
        ))

    return _render_spectrogram_video(clip_path, output_path, overlays,
                                     config.color_for(domain), config,
                                     window=(f_lo, f_hi), axis=axis,
                                     boxes=boxes)


def render_clip_poster(clip_path: str, poster_path: str,
                       thumbnail_path: str = "",
                       config: VideoConfig | None = None) -> tuple[str, str]:
    """
    Render a static spectrogram PNG for a clip, plus an optional thumbnail.

    Same two-step approach as the retired thumbnail script (showspectrumpic,
    then a scaled copy) but applied per event clip so the gallery gets a real
    cover image for each voice instead of one image per hour of tape.
    """
    config = config or VideoConfig()

    ok, err = run_ffmpeg([
        "-i", clip_path,
        "-lavfi",
        (f"showspectrumpic=s={config.poster_width}x{config.poster_height}:"
         f"legend=disable:start={config.min_freq}:stop={config.max_freq}:"
         f"fscale={config.freq_scale}:color={config.poster_color}:"
         f"drange={config.dynamic_range}:scale={config.gain_scale}"),
        "-frames:v", "1", "-y", poster_path,
    ])
    if not ok:
        return "", ""

    if not thumbnail_path:
        return poster_path, ""

    ok, _ = run_ffmpeg([
        "-i", poster_path,
        "-vf", f"scale={config.thumb_width}:{config.thumb_height}",
        "-frames:v", "1", "-y", thumbnail_path,
    ])
    return poster_path, (thumbnail_path if ok else "")


def render_clip(clip_path: str, event: dict, recording_meta: dict,
                video_config: VideoConfig | None = None,
                clip_config: ClipConfig | None = None) -> ClipRender:
    """Render every enabled artefact for a single event clip."""
    video_config = video_config or VideoConfig()
    clip_config = clip_config or ClipConfig()
    clip = Path(clip_path)
    result = ClipRender()

    if clip_config.make_video:
        out = str(clip.with_suffix(".mp4"))
        ok, err = render_clip_video(clip_path, out, event, recording_meta,
                                    video_config)
        if ok:
            result.video = out
        else:
            result.errors.append(f"video: {err}")

    if clip_config.make_poster:
        poster = str(clip.with_name(f"{clip.stem}-spectrogram.png"))
        thumb = str(clip.with_name(f"{clip.stem}-thumbnail.png"))
        result.poster, result.thumbnail = render_clip_poster(
            clip_path, poster, thumb, video_config)
        if not result.poster:
            result.errors.append("poster: showspectrumpic failed")

    if clip_config.make_gif and result.video:
        try:
            result.gif = video_to_gif(
                result.video,
                str(clip.with_name(f"{clip.stem}.gif")),
                width=video_config.gif_width, fps=video_config.gif_fps,
            )
        except Exception as exc:  # noqa: BLE001 - GIF is a nice-to-have
            result.errors.append(f"gif: {exc}")

    return result


def render_all_clips(clip_paths: list[str], events: list[dict],
                     recording_meta: dict,
                     video_config: VideoConfig | None = None,
                     clip_config: ClipConfig | None = None,
                     progress: bool = True) -> list[ClipRender]:
    """Render artefacts for every clip, reporting progress as it goes."""
    video_config = video_config or VideoConfig()
    clip_config = clip_config or ClipConfig()

    if not video_config.font_file:
        video_config.font_file = find_font()

    if (progress and clip_config.make_video and video_config.overlay_text
            and not can_draw_text()):
        print("    Note: this ffmpeg has no drawtext filter, so clip videos "
              "carry no burned-in label.")
        print("          Spectrogram, legend and audio are unaffected; the "
              "role and date stay in the")
        print("          filename, gallery and report. For labels: "
              "brew install ffmpeg-full")

    renders = []
    total = len(clip_paths)
    for i, (clip_path, event) in enumerate(zip(clip_paths, events), start=1):
        if progress:
            role = event.get("role", "event")
            print(f"    [{i}/{total}] {role} -> {Path(clip_path).name}")
        renders.append(render_clip(clip_path, event, recording_meta,
                                   video_config, clip_config))
    return renders


def build_event_type_reels(events: list[dict], output_dir: str,
                           clip_config: ClipConfig | None = None) -> dict[str, str]:
    """
    Concatenate every clip of the same ecological role into a single reel.

    One video per event type is the fastest way to hear/see what a role
    actually sounds like at a site, and it is what the gallery links as the
    "all dawn chorus participants" entry.
    """
    clip_config = clip_config or ClipConfig()
    if not clip_config.make_reels:
        return {}

    by_role: dict[str, list[str]] = {}
    for event in events:
        video = event.get("video_path")
        if video and Path(video).is_file():
            by_role.setdefault(event.get("role", "unclassified"), []).append(video)

    reel_dir = Path(output_dir) / "reels"
    reel_dir.mkdir(parents=True, exist_ok=True)

    reels = {}
    for role, videos in sorted(by_role.items()):
        if len(videos) < 2:
            continue  # a "reel" of one clip is just the clip
        out = str(reel_dir / f"reel_{role}.mp4")
        made = concat_videos(videos[:clip_config.reel_max_clips], out)
        if made:
            reels[role] = made
            print(f"    reel: {role} ({min(len(videos), clip_config.reel_max_clips)} clips)")

    return reels


def whole_file_video(wav_path: str, output_path: str = "",
                     location_text: str = "AudioMoth Recording",
                     date_text: str = "",
                     config: VideoConfig | None = None) -> str:
    """
    Render a spectrogram video for an entire recording.

    Kept as an explicit escape hatch for the old whole-file workflow (survey
    passes, presentation material). Event clips are the default path; this is
    the "I really do want the full hour" option in the wizard.
    """
    config = config or VideoConfig()
    out = output_path or str(Path(wav_path).with_suffix(".mp4"))

    overlays = [
        TextOverlay(text=location_text, x="25", y="25",
                    font_size=config.header_font_size),
        TextOverlay(text=date_text, x="W-tw-25", y="25",
                    font_size=config.date_font_size),
    ]
    ok, err = _render_spectrogram_video(wav_path, out, overlays,
                                        config.color, config)
    if not ok:
        raise RuntimeError(f"ffmpeg failed for {Path(wav_path).name}: {err}")
    return out


def check_renderer() -> tuple[bool, str]:
    """Report whether video rendering is available, and how complete it is."""
    if not have_ffmpeg():
        return False, "ffmpeg not found on PATH"
    if not can_draw_text():
        return True, "ffmpeg ready, but no drawtext filter (no burned-in labels)"
    font = find_font()
    return True, f"ffmpeg ready with labels (font: {font or 'fontconfig default'})"
