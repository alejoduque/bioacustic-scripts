"""
WAV clip extraction from detected events.

Reads only the frames it needs from disk and preserves the original sample
rate (no resampling), so clips stay faithful even when detection ran on a
downsampled copy.

Clips are filed by ecological role — clips/<domain>/<role>/ — so each type of
event in the parliament ends up with its own folder of evidence.
"""

import re
from dataclasses import replace
from pathlib import Path

import soundfile as sf

from .config import ClipConfig
from .detector import Event

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe(name: str) -> str:
    """Filesystem-safe fragment for use in file and directory names."""
    return _SAFE.sub("_", str(name)).strip("_") or "unknown"


def select_events(pairs: list[tuple[Event, dict]],
                  config: ClipConfig | None = None) -> list[tuple[Event, dict]]:
    """
    Keep only the events the user asked for.

    Filters on ecological role, acoustic domain and classification confidence,
    which is how the wizard offers "only rain and wind" or "only the chorus".
    """
    config = config or ClipConfig()
    roles = {r.lower() for r in config.roles}
    domains = {d.lower() for d in config.domains}

    kept = []
    for event, data in pairs:
        if roles and data.get("role", "").lower() not in roles:
            continue
        if domains and data.get("domain", "").lower() not in domains:
            continue
        if data.get("confidence", 0.0) < config.min_confidence:
            continue
        kept.append((event, data))
    return kept


def apply_fixed_windows(pairs: list[tuple[Event, dict]],
                        audio_duration_s: float,
                        config: ClipConfig | None = None
                        ) -> list[tuple[Event, dict]]:
    """
    Re-cut each kept event to a fixed-length window anchored on its onset, and
    drop events that would produce a near-duplicate of the previous window.

    The pre/post-roll model sizes the clip to the event, which is right when
    the event *is* the thing of interest but wrong for a survey: a 40-second
    insect chorus becomes a 70-second file, and ten events inside one minute
    become ten copies of that minute. A fixed window with a minimum onset
    separation gives one comparable file per moment worth looking at.

    Events are assumed sorted by onset, which detect_events guarantees.
    """
    config = config or ClipConfig()
    if config.fixed_duration_s <= 0:
        return pairs

    duration = config.fixed_duration_s
    pre = min(config.fixed_pre_s, duration)
    separation = (config.min_separation_s if config.min_separation_s > 0
                  else duration / 2.0)

    kept: list[tuple[Event, dict]] = []
    last_kept_onset = None

    for event, data in pairs:
        if last_kept_onset is not None and (event.onset_s - last_kept_onset) < separation:
            data["clip_skipped"] = "within min_separation of the previous clip"
            # No clip was cut, so the inherited pre/post-roll window would be a
            # window that does not exist on disk. Clear it rather than let the
            # catalogue advertise it.
            data["clip_start_s"] = None
            data["clip_end_s"] = None
            continue

        start = event.onset_s - pre
        # Slide, don't shrink, at the file edges: a window that runs past the
        # start or end is moved inward so every clip has the same length.
        start = max(0.0, min(start, max(0.0, audio_duration_s - duration)))
        end = min(audio_duration_s, start + duration)

        windowed = replace(event, clip_start_s=start, clip_end_s=end)
        data["clip_start_s"] = round(start, 3)
        data["clip_end_s"] = round(end, 3)
        kept.append((windowed, data))
        last_kept_onset = event.onset_s

    return kept


def clip_subdir(event_data: dict, organize_by: str = "role") -> Path:
    """Relative directory for an event's clip, based on its classification."""
    domain = _safe(event_data.get("domain", "unknown"))
    role = _safe(event_data.get("role", "unclassified"))

    if organize_by == "role":
        return Path("clips") / domain / role
    if organize_by == "domain":
        return Path("clips") / domain
    return Path("clips")


def clip_filename(event: Event, event_data: dict) -> str:
    """
    Self-describing clip name: index, role, and the span the file contains.

    Named by the CLIP window, not the event bounds. With fixed-length windows a
    30-minute event yields a 60-second file, and naming that file after the
    event would claim half an hour of audio that is not in it.
    """
    index = event_data.get("event_index", 0)
    role = _safe(event_data.get("role", "event"))
    return (f"event_{index:03d}_{role}_"
            f"{event.clip_start_s:.1f}s-{event.clip_end_s:.1f}s.wav")


def extract_clip(source_path: str, event: Event, event_data: dict,
                 output_dir: str, organize_by: str = "role") -> str:
    """Extract one event clip. Returns the path written."""
    info = sf.info(source_path)
    sr = info.samplerate

    start_frame = max(0, int(event.clip_start_s * sr))
    end_frame = int(event.clip_end_s * sr)
    n_frames = min(end_frame - start_frame, info.frames - start_frame)
    if n_frames <= 0:
        return ""

    audio, _ = sf.read(source_path, start=start_frame, frames=n_frames,
                       dtype="float64", always_2d=False)

    target_dir = Path(output_dir) / clip_subdir(event_data, organize_by)
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / clip_filename(event, event_data)

    sf.write(str(out_path), audio, sr)
    return str(out_path)


def extract_clips(source_path: str, pairs: list[tuple[Event, dict]],
                  output_dir: str,
                  config: ClipConfig | None = None) -> list[str]:
    """
    Extract clips for the given (Event, event_data) pairs.

    Pairs keep each Event next to its classification so the two can never drift
    out of alignment — the directory layout depends on the classification.
    """
    config = config or ClipConfig()
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    return [extract_clip(source_path, event, data, output_dir, config.organize_by)
            for event, data in pairs]
