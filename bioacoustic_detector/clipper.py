"""
WAV clip extraction from detected events.

Uses soundfile.read() with start/stop frame indices.
Preserves original sample rate (no resampling).
"""

from pathlib import Path

import numpy as np
import soundfile as sf

from .detector import Event


def extract_clip(source_path: str, event: Event, event_index: int,
                 output_dir: str) -> str:
    """
    Extract a WAV clip for a detected event.

    Reads only the needed frames from disk (efficient for large files).
    Preserves original sample rate.

    Returns path to the output WAV file.
    """
    info = sf.info(source_path)
    sr = info.samplerate

    start_frame = int(event.clip_start_s * sr)
    end_frame = int(event.clip_end_s * sr)
    n_frames = end_frame - start_frame

    # Clamp to file bounds
    start_frame = max(0, start_frame)
    n_frames = min(n_frames, info.frames - start_frame)

    audio, _ = sf.read(source_path, start=start_frame, frames=n_frames,
                       dtype='float64', always_2d=False)

    # Build output filename
    source_stem = Path(source_path).stem
    onset_str = f"{event.onset_s:.1f}"
    offset_str = f"{event.offset_s:.1f}"
    out_name = f"event_{event_index:03d}_{onset_str}s-{offset_str}s.wav"
    out_path = Path(output_dir) / out_name

    sf.write(str(out_path), audio, sr)
    return str(out_path)


def extract_all_clips(source_path: str, events: list[Event],
                      output_dir: str) -> list[str]:
    """Extract clips for all detected events. Returns list of output paths."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    paths = []
    for i, event in enumerate(events, start=1):
        path = extract_clip(source_path, event, i, output_dir)
        paths.append(path)
    return paths
