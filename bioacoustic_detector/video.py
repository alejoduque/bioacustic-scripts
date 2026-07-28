"""
Spectrogram MP4 generation mirroring make-spectrogram-movie-fixed.sh.

Uses the exact ffmpeg filter chain from the reference script with an
additional drawtext overlay for ecological classification labels.
"""

import subprocess
from pathlib import Path

from .config import VideoConfig


def generate_spectrogram_video(wav_path: str, output_path: str,
                               location_text: str = "AudioMoth Recording",
                               date_text: str = "",
                               classification_label: str = "",
                               config: VideoConfig | None = None) -> bool:
    """
    Generate a spectrogram MP4 video from a WAV clip.

    Mirrors the ffmpeg command in make-spectrogram-movie-fixed.sh (lines 163-169)
    with an optional third drawtext for the classification label.

    Returns True on success, False on failure.
    """
    if config is None:
        config = VideoConfig()

    # Escape special characters for ffmpeg drawtext
    def escape_text(text: str) -> str:
        return text.replace(":", "\\:").replace("'", "\\'")

    header = escape_text(location_text)
    date = escape_text(date_text)
    label = escape_text(classification_label)

    # Build the showspectrum + drawtext filter chain
    filters = (
        f"[0:a]showspectrum="
        f"s={config.width}x{config.height}:"
        f"legend={config.legend}:"
        f"start={config.min_freq}:"
        f"stop={config.max_freq}:"
        f"fscale={config.freq_scale}:"
        f"color={config.color}:"
        f"drange={config.dynamic_range}:"
        f"scale={config.gain_scale}:"
        f"slide={config.slide}"
    )

    # Header text (top-left)
    filters += (
        f",drawtext=text='{header}':"
        f"x=25:y=25:fontsize=24:fontcolor=white:"
        f"box=1:boxcolor=black@0.5:boxborderw=2"
    )

    # Date text (top-right)
    if date:
        filters += (
            f",drawtext=text='{date}':"
            f"x=W-tw-25:y=25:fontsize=20:fontcolor=white:"
            f"box=1:boxcolor=black@0.5:boxborderw=2"
        )

    # Classification label (bottom-left, yellow)
    if label:
        filters += (
            f",drawtext=text='{label}':"
            f"x=25:y=H-th-25:fontsize=20:fontcolor=yellow:"
            f"box=1:boxcolor=black@0.6:boxborderw=3"
        )

    filters += ",format=yuv420p[v]"

    cmd = [
        "ffmpeg",
        "-i", wav_path,
        "-filter_complex", filters,
        "-map", "[v]", "-map", "0:a",
        "-c:v", config.video_codec,
        "-preset", config.video_preset,
        "-crf", str(config.video_crf),
        "-c:a", config.audio_codec,
        "-b:a", config.audio_bitrate,
        "-movflags", "+faststart",
        "-y", output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def generate_all_videos(clip_paths: list[str], events_metadata: list[dict],
                        config: VideoConfig | None = None) -> list[str]:
    """
    Generate spectrogram videos for all clips.

    events_metadata should be a list of dicts with keys:
        - location_text, date_text, classification_label

    Returns list of video paths (empty string for failures).
    """
    video_paths = []
    for clip_path, meta in zip(clip_paths, events_metadata):
        video_path = str(Path(clip_path).with_suffix(".mp4"))
        success = generate_spectrogram_video(
            clip_path, video_path,
            location_text=meta.get("location_text", "AudioMoth Recording"),
            date_text=meta.get("date_text", ""),
            classification_label=meta.get("classification_label", ""),
            config=config,
        )
        video_paths.append(video_path if success else "")
    return video_paths
