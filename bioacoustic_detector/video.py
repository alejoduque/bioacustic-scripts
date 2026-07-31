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

from dataclasses import dataclass, field
from pathlib import Path

from .config import ClipConfig, VideoConfig
from .classifier import certainty_of
from .media import (OverlayTexts, TextOverlay, can_draw_text, concat_videos,
                    find_font, have_ffmpeg, run_ffmpeg, video_to_gif)


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


def _spectrum_filter(config: VideoConfig, color: str,
                     window: tuple[int, int] | None = None) -> str:
    """The showspectrum source filter, shared by clip and whole-file renders."""
    start, stop = window or (config.min_freq, config.max_freq)
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
                              column_px: int = 0) -> tuple[bool, str]:
    """
    Render a scrolling spectrogram video with the given text overlays.

    Overlays are dropped when the ffmpeg build has no drawtext filter (it needs
    libfreetype, which Homebrew's stock bottle omits). The spectrogram, its
    frequency legend and the audio are unaffected — only the burned-in caption
    is lost, and the same information stays in the filename, the gallery card,
    the report and events.json.
    """
    draw_text = config.overlay_text and can_draw_text()

    with OverlayTexts(config.font_file) as texts:
        chain = _spectrum_filter(config, color, window)
        # showspectrum stamps "CREATED BY LIBAVFILTER" into the bottom-left of
        # its legend. Painting over that strip is the only way to remove it
        # short of disabling the legend and redrawing the axes by hand; the
        # sample-rate note on the opposite side is left alone because it is
        # real information about the recording.
        chain += ",drawbox=x=0:y=ih-22:w=430:h=22:color=black:t=fill"
        if column_px > 0:
            chain += f",pad=iw+{column_px}:ih:0:0:color=black"
        if draw_text:
            for overlay in overlays:
                if overlay.text:
                    chain += "," + texts.filter_for(overlay)
        chain += ",format=yuv420p[v]"

        return run_ffmpeg(["-i", wav_path, "-filter_complex", chain,
                           *_encode_args(config, output_path)])


def metadata_block(event: dict, recording_meta: dict) -> str:
    """
    The metadata column, as one multi-line string.

    Everything known about the clip, grouped so a reader can see at a glance
    which lines are survey facts, which are recorder facts, and which are
    derived. Drawn as a single drawtext with newlines rather than one filter
    per line: a twenty-line column would otherwise mean twenty filters.

    Empty values are dropped, so a deployment with no GIS layer simply shows a
    shorter column instead of a list of blanks.
    """
    dt = recording_meta.get("datetime")
    sr = recording_meta.get("samplerate_hz") or 0
    temp = recording_meta.get("temperature_c")
    lat, lon = event.get("latitude"), event.get("longitude")

    groups = [
        ("SITE", [
            ("station", event.get("station_id")),
            ("locality", event.get("locality")),
            ("lat", f"{lat:.5f}" if lat is not None else ""),
            ("lon", f"{lon:.5f}" if lon is not None else ""),
            ("elevation", f"{event['elevation_m']:.0f} m"
             if event.get("elevation_m") is not None else ""),
            ("cover", recording_meta.get("habitat")),
            ("season", recording_meta.get("season")),
        ]),
        ("RECORDER", [
            ("device", recording_meta.get("audiomoth_id")),
            ("date", dt.strftime("%Y-%m-%d") if dt else ""),
            ("time", dt.strftime("%H:%M:%S") if dt else ""),
            ("temp", f"{temp:.1f} C" if temp is not None else ""),
            ("rate", f"{sr / 1000:.0f} kHz" if sr else ""),
            ("battery", f"{recording_meta['battery_v']:.2f} V"
             if recording_meta.get("battery_v") is not None else ""),
        ]),
        ("EVENT", [
            ("onset", f"{event.get('onset_s', 0):.2f} s"),
            ("length", f"{event.get('duration_s', 0):.2f} s"),

            ("centroid", f"{event.get('centroid', 0) / 1000:.2f} kHz"),
            ("in-band", f"{event.get('band_centroid', 0) / 1000:.2f} kHz"
             if event.get("band_centroid") else ""),
            ("crest", f"{event.get('band_crest', 0):.1f}"
             if event.get("band_crest") else ""),
            ("entropy", f"{event.get('band_entropy', 0):.3f}"
             if event.get("band_entropy") else ""),
            ("pulse", f"{event['pulse_rate_hz']:.1f} Hz"
             if event.get("periodicity", 0) >= 0.2
             and event.get("pulse_rate_hz") else ""),
        ]),
        ("INDICES", [
            ("ACI", f"{event.get('aci', 0):.1f}"),
            ("BIO", f"{event.get('bio', 0):.1f}"),
            ("NDSI", f"{event.get('ndsi', 0):+.3f}"),
            ("ADI", f"{event.get('adi', 0):.3f}"),
            ("AEI", f"{event.get('aei', 0):.3f}"),
        ]),
    ]

    # Each contributing band on its own line. A pond at night runs three bands
    # at once, and squeezing them onto one line simply ran off the column.
    shares = event.get("band_shares") or {}
    if shares:
        # Pre-formatted into the key so the share is not squeezed against the
        # band name by the label column's fixed 10-character pad.
        band_rows = [(f"  {name.replace('_', ' '):<17}{share:>3.0%}", "")
                     for name, share in shares.items()]
        for name, rows in groups:
            if name == "EVENT":
                rows[2:2] = [("bands", "")] + band_rows
                break

    # drawtext will not wrap, so anything longer than the column gets cut off
    # mid-word — as "…ciénagas naturales" did. Fold instead.
    width = 30
    lines = []
    for heading, rows in groups:
        # An empty value normally means "nothing measured", so the row is
        # dropped. Rows already formatted whole — the per-band shares, and the
        # heading above them — are indented and kept.
        present = [(k, str(v)) for k, v in rows
                   if v not in (None, "", "None") or k.startswith("  ")
                   or k == "bands"]
        if not present:
            continue
        if lines:
            lines.append("")
        lines.append(heading)
        for key, value in present:
            row = f"{key:<10}{value}" if value else key
            while len(row) > width:
                cut = row.rfind(" ", 0, width)
                cut = cut if cut > 10 else width
                lines.append(row[:cut])
                row = " " * 10 + row[cut:].lstrip()
            lines.append(row)
    return "\n".join(lines)


def render_clip_video(clip_path: str, output_path: str, event: dict,
                      recording_meta: dict,
                      config: VideoConfig | None = None) -> tuple[bool, str]:
    """
    Render one event clip as a spectrogram video.

    Overlays, clockwise from top-left:
      habitat  |  recording date + the clip's offset inside the recording
      ecological role, confidence, dominant band  |  NDSI / ACI
    """
    config = config or VideoConfig()

    domain = event.get("domain", "")
    confidence = event.get("confidence", 0.0)
    certainty = event.get("certainty") or certainty_of(confidence)

    # The caption NAMES THE EVENT and then says how far that naming can be
    # trusted. An earlier version printed only "unclassified", which told a
    # viewer nothing about what they were looking at; the qualifier stays
    # because the rules are uncalibrated. Everything measured now lives in the
    # metadata column, so the old bottom-right line was both a duplicate and a
    # collision with showspectrum's own TIME axis label.
    qualifier = {"probable": "probable",
                 "candidate": "candidate",
                 "unclassified": "unverified"}.get(certainty, certainty)
    # Every voice the event carries, not only the loudest. An event whose
    # energy splits 44/31/24 across three bands is a soundscape, and naming it
    # after the plurality is what made a pond full of frogs read as insects.
    names = event.get("roles") or [event.get("role", "event")]
    inferred = " + ".join(n.replace("_", " ") for n in names)
    inferred += f"  [{qualifier} {confidence:.0%}]"

    rec_dt = recording_meta.get("datetime")
    date_text = rec_dt.strftime("%d %B %Y %H:%M") if rec_dt else ""
    onset = event.get("onset_s", 0.0)
    date_text = (f"{date_text}  (+{onset:.0f}s)" if date_text
                 else f"+{onset:.0f}s into recording")

    column_px = config.metadata_column_px
    # Anchor the spectrum-side overlays to the plot, not to the padded frame,
    # or the right-aligned date would land inside the metadata column.
    plot_right = f"(W-{column_px})" if column_px > 0 else "W"

    overlays = [
        TextOverlay(
            text=str(recording_meta.get("habitat") or "AudioMoth Recording"),
            x="25", y="25", font_size=config.header_font_size,
        ),
        TextOverlay(
            text=date_text,
            x=f"{plot_right}-tw-25", y="25", font_size=config.date_font_size,
        ),
        TextOverlay(
            text=inferred,
            x="25", y="H-th-25", font_size=config.label_font_size,
        ),
    ]

    if column_px > 0:
        overlays.append(TextOverlay(
            text=metadata_block(event, recording_meta),
            x=f"W-{column_px}+18", y="24",
            font_size=config.column_font_size,
            line_spacing=config.column_line_spacing,
        ))

    return _render_spectrogram_video(clip_path, output_path, overlays,
                                     config.color_for(domain), config,
                                     window=freq_window(event, config),
                                     column_px=column_px)


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
