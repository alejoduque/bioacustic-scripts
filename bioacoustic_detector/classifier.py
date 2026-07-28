"""
Deep ecology taxonomy classification.

Events are classified by ecological role, not species identity.
All acoustic participants (biophony, geophony, anthrophony) have
inherent ecological value and are cataloged as members of a
"parliament of the living."
"""

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from .config import SpectralConfig


# Ecological domains
DOMAIN_BIOPHONY = "biophony"
DOMAIN_GEOPHONY = "geophony"
DOMAIN_ANTHROPHONY = "anthrophony"
DOMAIN_TRANSITION = "transition"

# Ecological roles (deep ecology taxonomy)
ROLES = {
    # Biophonic voices (the Parliament)
    "dawn_chorus_participant": DOMAIN_BIOPHONY,
    "dusk_chorus_participant": DOMAIN_BIOPHONY,
    "nocturnal_voice": DOMAIN_BIOPHONY,
    "territorial_announcement": DOMAIN_BIOPHONY,
    "alarm_or_alert": DOMAIN_BIOPHONY,
    "insect_chorus": DOMAIN_BIOPHONY,
    "amphibian_assembly": DOMAIN_BIOPHONY,
    # Geophonic elements (Voice of the Earth)
    "rain_event": DOMAIN_GEOPHONY,
    "wind_event": DOMAIN_GEOPHONY,
    "water_flow": DOMAIN_GEOPHONY,
    # Anthrophonic intrusions
    "mechanical_intrusion": DOMAIN_ANTHROPHONY,
    "aircraft_passage": DOMAIN_ANTHROPHONY,
    # Acoustic transitions (temporal ecotones)
    "silence_to_activity": DOMAIN_TRANSITION,
    "activity_to_silence": DOMAIN_TRANSITION,
    "community_shift": DOMAIN_TRANSITION,
}


@dataclass
class Classification:
    """Result of classifying an acoustic event."""
    role: str
    domain: str
    confidence: float      # 0-1
    dominant_band: str     # Name of the dominant frequency band
    reasoning: str         # Human-readable explanation


def classify_event(onset_s: float, offset_s: float,
                   centroid: float, flatness: float, peak_flux: float,
                   band_energies: dict[str, float],
                   recording_datetime: datetime | None = None,
                   prev_event_flux: float | None = None,
                   config: SpectralConfig | None = None) -> Classification:
    """
    Classify an acoustic event by its ecological role.

    Uses: time of day, dominant frequency band, spectral flatness
    (tonal vs noise-like), event duration, and energy distribution.
    """
    if config is None:
        config = SpectralConfig()

    duration = offset_s - onset_s

    # Determine dominant band
    dominant_band = max(band_energies, key=band_energies.get)
    total_energy = sum(band_energies.values())
    if total_energy > 0:
        dominant_ratio = band_energies[dominant_band] / total_energy
    else:
        dominant_ratio = 0.0

    # Get hour for diel classification
    hour = recording_datetime.hour if recording_datetime else 12

    # Classify based on features
    role, confidence, reasoning = _classify_features(
        hour, duration, centroid, flatness, peak_flux,
        dominant_band, dominant_ratio, band_energies,
        prev_event_flux,
    )

    return Classification(
        role=role,
        domain=ROLES[role],
        confidence=confidence,
        dominant_band=dominant_band,
        reasoning=reasoning,
    )


def _classify_features(hour: int, duration: float,
                       centroid: float, flatness: float, peak_flux: float,
                       dominant_band: str, dominant_ratio: float,
                       band_energies: dict[str, float],
                       prev_event_flux: float | None) -> tuple[str, float, str]:
    """
    Rule-based classification using spectral features.

    Returns (role, confidence, reasoning).
    """
    # Transition detection: large flux change from previous event
    if prev_event_flux is not None:
        flux_ratio = peak_flux / max(prev_event_flux, 1e-10)
        if flux_ratio > 5.0:
            return ("silence_to_activity", 0.7,
                    f"Flux increased {flux_ratio:.1f}x from previous event")
        if flux_ratio < 0.2:
            return ("activity_to_silence", 0.7,
                    f"Flux decreased to {flux_ratio:.2f}x of previous event")

    # Geophonic: noise-like (high flatness) + low frequency dominance
    if flatness > 0.3 and dominant_band == "geophony":
        if duration > 30:
            return ("rain_event", 0.75,
                    f"Broadband noise (flatness={flatness:.2f}) in geophony band, long duration")
        elif duration > 10:
            return ("wind_event", 0.65,
                    f"Broadband noise in geophony band, moderate duration")
        else:
            return ("water_flow", 0.5,
                    f"Noise-like signal in geophony band")

    # Anthrophonic: low frequency + moderate flatness + specific patterns
    if dominant_band == "geophony" and flatness > 0.15 and centroid < 1500:
        if duration > 20:
            return ("mechanical_intrusion", 0.6,
                    f"Low-frequency sustained noise (centroid={centroid:.0f}Hz)")
        elif 5 < duration < 60 and centroid < 800:
            return ("aircraft_passage", 0.55,
                    f"Low-frequency passage pattern (centroid={centroid:.0f}Hz)")

    # Biophonic classification by time of day and frequency
    # Dawn chorus: 4:30-7:00, mid-frequency birds
    if 4 <= hour <= 7 and dominant_band in ("biophony_mid", "biophony_low"):
        return ("dawn_chorus_participant", 0.8,
                f"Mid-frequency activity during dawn hours (h={hour})")

    # Dusk chorus: 17:00-19:30
    if 17 <= hour <= 19 and dominant_band in ("biophony_mid", "biophony_low"):
        return ("dusk_chorus_participant", 0.75,
                f"Mid-frequency activity during dusk hours (h={hour})")

    # Nocturnal voices: 20:00-4:00
    if hour >= 20 or hour < 4:
        if dominant_band == "biophony_low" and flatness < 0.15:
            return ("amphibian_assembly", 0.7,
                    f"Low-frequency tonal signals at night (flatness={flatness:.2f})")
        if dominant_band in ("biophony_high", "ultrasonic"):
            return ("nocturnal_voice", 0.65,
                    f"High-frequency nocturnal activity")
        if dominant_band == "biophony_mid":
            return ("nocturnal_voice", 0.6,
                    f"Mid-frequency nocturnal activity")

    # Insect chorus: high frequency, high flatness, sustained
    if dominant_band in ("biophony_high", "ultrasonic") and duration > 10:
        return ("insect_chorus", 0.7,
                f"Sustained high-frequency activity (band={dominant_band})")

    # Amphibian assembly: low biophony, tonal, often sustained
    if dominant_band == "biophony_low" and flatness < 0.15 and duration > 5:
        return ("amphibian_assembly", 0.65,
                f"Tonal low-frequency sustained activity")

    # Alarm/alert: short, high flux, mid-frequency
    if duration < 5 and peak_flux > 0 and dominant_band == "biophony_mid":
        return ("alarm_or_alert", 0.5,
                f"Short, intense mid-frequency event")

    # Territorial: mid-frequency, moderate duration, tonal
    if dominant_band == "biophony_mid" and flatness < 0.2 and 2 < duration < 30:
        return ("territorial_announcement", 0.55,
                f"Tonal mid-frequency vocalization")

    # Community shift: multiple bands active
    active_bands = sum(1 for v in band_energies.values() if v > 0)
    if active_bands >= 3 and dominant_ratio < 0.4:
        return ("community_shift", 0.45,
                f"Energy spread across {active_bands} bands")

    # Default: classify by dominant band
    if dominant_band in ("biophony_mid", "biophony_low"):
        return ("territorial_announcement", 0.3,
                f"Unspecified biophonic event in {dominant_band}")
    if dominant_band in ("biophony_high", "ultrasonic"):
        return ("insect_chorus", 0.3,
                f"Unspecified high-frequency biophonic event")

    return ("community_shift", 0.2,
            f"Unclassified acoustic event (band={dominant_band})")


def parliament_summary(classifications: list[Classification]) -> dict:
    """
    Generate a "Parliament of the Living" summary.

    Returns:
        - total_voices: total number of events
        - domain_percentages: biophonic/geophonic/anthrophonic/transition %
        - role_counts: count per role
        - democracy_index: Shannon entropy of role distribution (acoustic democracy)
        - niche_partitioning: score based on band usage diversity
    """
    if not classifications:
        return {
            "total_voices": 0,
            "domain_percentages": {},
            "role_counts": {},
            "democracy_index": 0.0,
            "niche_partitioning": 0.0,
        }

    total = len(classifications)

    # Domain percentages
    domain_counts = {}
    for c in classifications:
        domain_counts[c.domain] = domain_counts.get(c.domain, 0) + 1
    domain_pcts = {d: (count / total) * 100
                   for d, count in domain_counts.items()}

    # Role counts
    role_counts = {}
    for c in classifications:
        role_counts[c.role] = role_counts.get(c.role, 0) + 1

    # Shannon entropy (democracy index)
    proportions = np.array(list(role_counts.values())) / total
    proportions = proportions[proportions > 0]
    democracy_index = float(-np.sum(proportions * np.log2(proportions)))

    # Niche partitioning: diversity of dominant bands used
    band_counts = {}
    for c in classifications:
        band_counts[c.dominant_band] = band_counts.get(c.dominant_band, 0) + 1
    band_props = np.array(list(band_counts.values())) / total
    band_props = band_props[band_props > 0]
    niche_partitioning = float(-np.sum(band_props * np.log2(band_props)))

    return {
        "total_voices": total,
        "domain_percentages": domain_pcts,
        "role_counts": role_counts,
        "democracy_index": round(democracy_index, 3),
        "niche_partitioning": round(niche_partitioning, 3),
    }
