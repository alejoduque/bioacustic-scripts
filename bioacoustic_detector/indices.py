"""
Ecoacoustic indices: ACI, BIO, NDSI, ADI, AEI.

Computed per clip and per full recording to characterize acoustic diversity
and community structure.
"""

import numpy as np

from .config import SpectralConfig


def acoustic_complexity_index(magnitude: np.ndarray) -> float:
    """
    Acoustic Complexity Index (ACI) — Pieretti et al. 2011.

    Measures temporal variability within frequency bins.
    High ACI = complex biophonic activity; low ACI = constant noise.
    """
    if magnitude.shape[0] < 2:
        return 0.0

    # Sum of absolute differences / sum of values, per frequency bin
    diffs = np.abs(np.diff(magnitude, axis=0))
    bin_sums = np.sum(magnitude[:-1], axis=0)
    bin_sums = np.where(bin_sums == 0, 1.0, bin_sums)
    aci_per_bin = np.sum(diffs, axis=0) / bin_sums
    return float(np.sum(aci_per_bin))


def bioacoustic_index(magnitude: np.ndarray, freqs: np.ndarray,
                      min_freq: float = 2000.0,
                      max_freq: float = 8000.0) -> float:
    """
    Bioacoustic Index (BIO) — Boelman et al. 2007.

    Area under the mean spectrum curve between min_freq and max_freq,
    referenced to the minimum value in that range.
    """
    mask = (freqs >= min_freq) & (freqs <= max_freq)
    if not np.any(mask):
        return 0.0

    mean_spectrum = np.mean(magnitude[:, mask], axis=0)
    # Convert to dB
    mean_db = 20 * np.log10(np.maximum(mean_spectrum, 1e-10))
    # Reference to minimum
    mean_db -= np.min(mean_db)
    # Area under curve
    return float(np.sum(mean_db))


def normalized_difference_soundscape_index(
        magnitude: np.ndarray, freqs: np.ndarray,
        anthro_range: tuple[float, float] = (1000.0, 2000.0),
        bio_range: tuple[float, float] = (2000.0, 8000.0)) -> float:
    """
    Normalized Difference Soundscape Index (NDSI) — Kasten et al. 2012.

    NDSI = (bio - anthro) / (bio + anthro)
    Range: -1 (all anthrophony) to +1 (all biophony).
    """
    anthro_mask = (freqs >= anthro_range[0]) & (freqs < anthro_range[1])
    bio_mask = (freqs >= bio_range[0]) & (freqs < bio_range[1])

    anthro_energy = float(np.sum(np.mean(magnitude[:, anthro_mask] ** 2, axis=0))) if np.any(anthro_mask) else 0.0
    bio_energy = float(np.sum(np.mean(magnitude[:, bio_mask] ** 2, axis=0))) if np.any(bio_mask) else 0.0

    total = bio_energy + anthro_energy
    if total == 0:
        return 0.0
    return (bio_energy - anthro_energy) / total


def acoustic_diversity_index(magnitude: np.ndarray, freqs: np.ndarray,
                             freq_step: float = 1000.0,
                             max_freq: float = 10000.0,
                             threshold_db: float = -50.0) -> float:
    """
    Acoustic Diversity Index (ADI) — Villanueva-Rivera et al. 2011.

    Shannon entropy of the proportion of frequency bands above a threshold.
    Higher = more diverse acoustic activity across frequency bands.
    """
    # Compute mean power in dB per frequency band
    bands = np.arange(0, max_freq, freq_step)
    proportions = []

    for lo in bands:
        hi = lo + freq_step
        mask = (freqs >= lo) & (freqs < hi)
        if not np.any(mask):
            proportions.append(0.0)
            continue
        # Proportion of frames above threshold in this band
        band_power_db = 10 * np.log10(np.maximum(np.mean(magnitude[:, mask] ** 2, axis=1), 1e-20))
        prop = np.mean(band_power_db > threshold_db)
        proportions.append(prop)

    proportions = np.array(proportions)
    total = np.sum(proportions)
    if total == 0:
        return 0.0

    p = proportions / total
    p = p[p > 0]
    return float(-np.sum(p * np.log(p)))


def acoustic_evenness_index(magnitude: np.ndarray, freqs: np.ndarray,
                            freq_step: float = 1000.0,
                            max_freq: float = 10000.0,
                            threshold_db: float = -50.0) -> float:
    """
    Acoustic Evenness Index (AEI) — Villanueva-Rivera et al. 2011.

    Gini coefficient of frequency band activity. Lower = more even.
    """
    bands = np.arange(0, max_freq, freq_step)
    activities = []

    for lo in bands:
        hi = lo + freq_step
        mask = (freqs >= lo) & (freqs < hi)
        if not np.any(mask):
            activities.append(0.0)
            continue
        band_power_db = 10 * np.log10(np.maximum(np.mean(magnitude[:, mask] ** 2, axis=1), 1e-20))
        activities.append(float(np.mean(band_power_db > threshold_db)))

    activities = np.array(sorted(activities))
    n = len(activities)
    if n == 0 or np.sum(activities) == 0:
        return 0.0

    # Gini coefficient
    index = np.arange(1, n + 1)
    return float(np.sum((2 * index - n - 1) * activities) / (n * np.sum(activities)))


def compute_all_indices(magnitude: np.ndarray, freqs: np.ndarray,
                        config: SpectralConfig | None = None) -> dict:
    """Compute all ecoacoustic indices for a spectrogram."""
    if config is None:
        config = SpectralConfig()

    return {
        "aci": round(acoustic_complexity_index(magnitude), 4),
        "bio": round(bioacoustic_index(magnitude, freqs), 4),
        "ndsi": round(normalized_difference_soundscape_index(magnitude, freqs), 4),
        "adi": round(acoustic_diversity_index(magnitude, freqs), 4),
        "aei": round(acoustic_evenness_index(magnitude, freqs), 4),
    }
