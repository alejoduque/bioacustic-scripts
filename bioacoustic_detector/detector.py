"""
Adaptive-threshold event detection from spectral flux.

Uses running median + scaled MAD (median absolute deviation) over a
configurable baseline window. Events that are too short are discarded,
nearby events are merged, and clips get pre/post-roll padding.
"""

from dataclasses import dataclass

import numpy as np

from .config import DetectorConfig


@dataclass
class Event:
    """A detected acoustic event."""
    onset_s: float        # Event onset in seconds
    offset_s: float       # Event offset in seconds
    clip_start_s: float   # Clip start (with pre-roll)
    clip_end_s: float     # Clip end (with post-roll)
    peak_flux: float      # Maximum spectral flux during event
    mean_flux: float      # Mean spectral flux during event
    onset_frame: int
    offset_frame: int


def running_median_mad(flux: np.ndarray, window_frames: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute running median and MAD (median absolute deviation) over a window.

    Uses a causal window (looks back only) so detection is causal.
    For the initial frames where the window is not full, uses all available data.
    """
    n = len(flux)
    median = np.empty(n)
    mad = np.empty(n)

    for i in range(n):
        start = max(0, i - window_frames + 1)
        window = flux[start:i + 1]
        med = np.median(window)
        median[i] = med
        mad[i] = np.median(np.abs(window - med))

    return median, mad


def detect_events(flux: np.ndarray, frame_times: np.ndarray,
                  audio_duration_s: float,
                  config: DetectorConfig | None = None) -> list[Event]:
    """
    Detect acoustic events from spectral flux using adaptive thresholding.

    Steps:
    1. Compute running median + MAD baseline
    2. Threshold: flux > median + factor * mad_scale * MAD
    3. Find contiguous regions above threshold
    4. Merge events closer than merge_gap
    5. Discard merged events shorter than min_event_duration
    6. Add pre/post-roll and enforce max clip duration
    """
    if config is None:
        config = DetectorConfig()

    if len(flux) == 0:
        return []

    # Compute time resolution from frame_times
    if len(frame_times) > 1:
        dt = frame_times[1] - frame_times[0]
    else:
        return []

    window_frames = max(1, int(config.baseline_window_s / dt))

    # Adaptive threshold
    median, mad = running_median_mad(flux, window_frames)
    threshold = median + config.threshold_factor * config.mad_scale * mad

    # Find frames above threshold
    above = flux > threshold

    # Find contiguous regions
    raw_events = _find_regions(above, frame_times, flux)

    if not raw_events:
        return []

    # Merge events within merge_gap BEFORE filtering by duration
    merged = _merge_events(raw_events, config.merge_gap_s)

    # Filter by minimum duration after merging
    merged = [e for e in merged
              if (e["offset_s"] - e["onset_s"]) >= config.min_event_duration_s]

    # Build Event objects with pre/post-roll
    events = []
    for e in merged:
        clip_start = max(0.0, e["onset_s"] - config.pre_roll_s)
        clip_end = min(audio_duration_s, e["offset_s"] + config.post_roll_s)
        # Enforce max clip duration
        if (clip_end - clip_start) > config.max_clip_duration_s:
            clip_end = clip_start + config.max_clip_duration_s

        events.append(Event(
            onset_s=e["onset_s"],
            offset_s=e["offset_s"],
            clip_start_s=clip_start,
            clip_end_s=clip_end,
            peak_flux=e["peak_flux"],
            mean_flux=e["mean_flux"],
            onset_frame=e["onset_frame"],
            offset_frame=e["offset_frame"],
        ))

    return events


def _find_regions(above: np.ndarray, frame_times: np.ndarray,
                  flux: np.ndarray) -> list[dict]:
    """Find contiguous regions where above is True."""
    regions = []
    in_region = False
    start_idx = 0

    for i in range(len(above)):
        if above[i] and not in_region:
            in_region = True
            start_idx = i
        elif not above[i] and in_region:
            in_region = False
            region_flux = flux[start_idx:i]
            regions.append({
                "onset_s": frame_times[start_idx],
                "offset_s": frame_times[i - 1],
                "onset_frame": start_idx,
                "offset_frame": i - 1,
                "peak_flux": float(np.max(region_flux)),
                "mean_flux": float(np.mean(region_flux)),
            })

    # Handle region that extends to end
    if in_region:
        region_flux = flux[start_idx:]
        regions.append({
            "onset_s": frame_times[start_idx],
            "offset_s": frame_times[-1],
            "onset_frame": start_idx,
            "offset_frame": len(above) - 1,
            "peak_flux": float(np.max(region_flux)),
            "mean_flux": float(np.mean(region_flux)),
        })

    return regions


def _merge_events(events: list[dict], merge_gap_s: float) -> list[dict]:
    """Merge events that are within merge_gap_s of each other."""
    if not events:
        return []

    merged = [events[0].copy()]

    for e in events[1:]:
        prev = merged[-1]
        if (e["onset_s"] - prev["offset_s"]) <= merge_gap_s:
            # Merge: extend previous event
            prev["offset_s"] = e["offset_s"]
            prev["offset_frame"] = e["offset_frame"]
            prev["peak_flux"] = max(prev["peak_flux"], e["peak_flux"])
            # Recompute mean as weighted average (approximate)
            prev["mean_flux"] = (prev["mean_flux"] + e["mean_flux"]) / 2.0
        else:
            merged.append(e.copy())

    return merged
