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


def _spectrum_filter(config: VideoConfig, color: str) -> str:
    """The showspectrum source filter, shared by clip and whole-file renders."""
    return (
        f"[0:a]showspectrum="
        f"s={config.width}x{config.height}:"
        f"legend={config.legend}:"
        f"start={config.min_freq}:"
        f"stop={config.max_freq}:"
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
                              config: VideoConfig) -> tuple[bool, str]:
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
        chain = _spectrum_filter(config, color)
        if draw_text:
            for overlay in overlays:
                if overlay.text:
                    chain += "," + texts.filter_for(overlay)
        chain += ",format=yuv420p[v]"

        return run_ffmpeg(["-i", wav_path, "-filter_complex", chain,
                           *_encode_args(config, output_path)])


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
    role = event.get("role", "event").replace("_", " ").title()
    confidence = event.get("confidence", 0.0)
    band = event.get("dominant_band", "").replace("_", " ")

    rec_dt = recording_meta.get("datetime")
    date_text = rec_dt.strftime("%d %B %Y %H:%M") if rec_dt else ""
    onset = event.get("onset_s", 0.0)
    if date_text:
        date_text = f"{date_text}  (+{onset:.0f}s)"
    else:
        date_text = f"+{onset:.0f}s into recording"

    overlays = [
        TextOverlay(
            text=str(recording_meta.get("habitat") or "AudioMoth Recording"),
            x="25", y="25", font_size=config.header_font_size,
        ),
        TextOverlay(
            text=date_text,
            x="W-tw-25", y="25", font_size=config.date_font_size,
        ),
        TextOverlay(
            text=f"{role} ({confidence:.0%}) | {band}",
            x="25", y="H-th-25", font_size=config.label_font_size,
        ),
        TextOverlay(
            text=f"NDSI {event.get('ndsi', 0):+.2f}  ACI {event.get('aci', 0):.1f}",
            x="W-tw-25", y="H-th-25", font_size=config.label_font_size - 4,
        ),
    ]

    return _render_spectrogram_video(clip_path, output_path, overlays,
                                     config.color_for(domain), config)


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
