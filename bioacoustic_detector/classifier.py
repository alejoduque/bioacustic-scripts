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
    "bat_echolocation": DOMAIN_BIOPHONY,
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


# --- Rule thresholds -------------------------------------------------------
#
# These are the knobs that decide which role an event gets. They are stated
# here rather than inline because they are calibration parameters, not
# implementation details: they encode assumptions about a site that should be
# checked against real recordings before the labels are trusted in bulk.
#
# Measured on synthetic band-limited rain noise (60-1900 Hz) during testing:
# flatness came out at 0.21 and 0.29, i.e. below GEOPHONY_FLATNESS, so the
# rain/wind/water rules never fired and the events fell through to the
# transition and fallback rules. Two properties of the features explain it and
# both matter when calibrating:
#
#   * Spectral flatness is computed across the WHOLE spectrum, so a signal that
#     is perfectly noise-like inside its own band still scores low when it
#     occupies only part of the range. It measures "is this recording noisy",
#     not "is this event noisy".
#   * Spectral centroid is magnitude-weighted over the whole spectrum, so a
#     wide low-level noise floor pulls it upward. The same rain events above
#     reported centroids of 6.5 and 7.7 kHz despite having no energy at all
#     above 2 kHz, which is why the anthrophony rule (centroid < 1500) also
#     missed them.
#
# Neither is a bug in the arithmetic; they are the documented behaviour of
# global spectral descriptors applied to band-limited events. Retuning these
# numbers against annotated field recordings is the intended fix.

GEOPHONY_FLATNESS = 0.30       # above this, a geophony-dominant event is "noise-like"
ANTHROPHONY_FLATNESS = 0.15    # above this, with a low centroid, suspect machinery
ANTHROPHONY_CENTROID_HZ = 1500
AIRCRAFT_CENTROID_HZ = 800
TONAL_FLATNESS = 0.15          # below this, treat as tonal (amphibian, territorial)
TERRITORIAL_FLATNESS = 0.20
TRANSITION_RISE = 5.0          # flux ratio vs previous event -> silence_to_activity
TRANSITION_FALL = 0.2          # flux ratio vs previous event -> activity_to_silence
RAIN_MIN_DURATION_S = 30.0
WIND_MIN_DURATION_S = 10.0
COMMUNITY_SHIFT_BANDS = 3      # active bands needed to call it a community shift
COMMUNITY_SHIFT_DOMINANCE = 0.4  # ...and no single band may exceed this share
BAT_PASS_MAX_DURATION_S = 5.0     # above this, ultrasonic energy is not a pass
INSECT_CHORUS_MIN_DURATION_S = 10.0  # sustained ultrasonic = stridulating insects


def is_ultrasonic_band(band: str) -> bool:
    """
    True for any band above the audible range, in either band table.

    Band names differ between the audible table ("ultrasonic") and the
    ultrasonic table ("ultrasonic_low/mid/high"), so match on the prefix rather
    than on an exact name — otherwise every rule silently stops firing the
    moment someone enables ultrasonic mode.
    """
    return band.startswith("ultrasonic")


def is_bat_band(band: str) -> bool:
    """
    True only for the resolved bat bands of the ultrasonic table.

    Deliberately narrower than is_ultrasonic_band(). The audible table's top
    band is also called "ultrasonic", but it covers 16-24 kHz — which at a
    48 kHz analysis rate is mostly katydids and cicadas, and is the ceiling of
    what that rate can represent rather than evidence of echolocation. Calling
    those events bat passes at 0.8 confidence would be overclaiming; only the
    native-rate bands (ultrasonic_low/mid/high) support that reading.
    """
    return band.startswith("ultrasonic_")


def is_high_band(band: str) -> bool:
    """True for the top of the audible range and anything above it."""
    return band == "biophony_high" or is_ultrasonic_band(band)


# How far a role assignment can be trusted. Validation against AnuraSet and the
# Manakai field recordings established that `role` is a hypothesis from
# uncalibrated thresholds while `dominant_band` is a measurement, and that the
# two must not be presented as though they were the same kind of claim.
#
# Derived from the confidence each rule branch returns, which is itself a
# hand-assigned constant ranking rules by specificity — never a probability.
CERTAINTY_PROBABLE = 0.6    # a specific rule matched on several features
CERTAINTY_CANDIDATE = 0.35  # a rule matched, but one known to over-claim


def certainty_of(confidence: float) -> str:
    """
    Bucket a rule's confidence into a claim strength a reader can act on.

    unclassified  the fallback branches — no rule matched, the event is filed
                  under its nearest neighbour and means nothing more than that
    candidate     a rule matched but is known to over-claim (bat_echolocation
                  on a band that also carries katydids, for instance)
    probable      a specific rule matched on several features
    """
    if confidence >= CERTAINTY_PROBABLE:
        return "probable"
    if confidence > CERTAINTY_CANDIDATE:
        return "candidate"
    return "unclassified"


@dataclass
class Classification:
    """Result of classifying an acoustic event."""
    role: str
    domain: str
    confidence: float      # 0-1, a rule-specificity rank, NOT a probability
    dominant_band: str     # Name of the dominant frequency band (measured)
    reasoning: str         # Human-readable explanation

    @property
    def certainty(self) -> str:
        """How far this assignment can be trusted — see certainty_of()."""
        return certainty_of(self.confidence)


def classify_event(onset_s: float, offset_s: float,
                   centroid: float, flatness: float, peak_flux: float,
                   band_energies: dict[str, float],
                   recording_datetime: datetime | None = None,
                   prev_event_flux: float | None = None,
                   config: SpectralConfig | None = None,
                   band_features: dict | None = None) -> Classification:
    """
    Classify an acoustic event by its ecological role.

    Uses: time of day, dominant frequency band, spectral flatness
    (tonal vs noise-like), event duration, and energy distribution.

    `band_features` carries the within-band and temporal measurements from
    spectral.event_band_features (`band_crest`, `band_entropy`, `periodicity`,
    `pulse_rate_hz`). They are optional so older callers keep working, but
    without them the low band cannot be resolved — see `_classify_low_band`.
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
        prev_event_flux, band_features or {},
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
                       prev_event_flux: float | None,
                       band_features: dict | None = None) -> tuple[str, float, str]:
    """
    Rule-based classification using spectral features.

    Returns (role, confidence, reasoning).
    """
    # Transition detection: large flux change from previous event
    if prev_event_flux is not None:
        flux_ratio = peak_flux / max(prev_event_flux, 1e-10)
        if flux_ratio > TRANSITION_RISE:
            return ("silence_to_activity", 0.7,
                    f"Flux increased {flux_ratio:.1f}x from previous event")
        if flux_ratio < TRANSITION_FALL:
            return ("activity_to_silence", 0.7,
                    f"Flux decreased to {flux_ratio:.2f}x of previous event")

    # Geophonic: noise-like (high flatness) + low frequency dominance
    if flatness > GEOPHONY_FLATNESS and dominant_band == "geophony":
        if duration > RAIN_MIN_DURATION_S:
            return ("rain_event", 0.75,
                    f"Broadband noise (flatness={flatness:.2f}) in geophony band, long duration")
        elif duration > WIND_MIN_DURATION_S:
            return ("wind_event", 0.65,
                    f"Broadband noise in geophony band, moderate duration")
        else:
            return ("water_flow", 0.5,
                    f"Noise-like signal in geophony band")

    # Anthrophonic: low frequency + moderate flatness + specific patterns
    if (dominant_band == "geophony" and flatness > ANTHROPHONY_FLATNESS
            and centroid < ANTHROPHONY_CENTROID_HZ):
        if duration > 20:
            return ("mechanical_intrusion", 0.6,
                    f"Low-frequency sustained noise (centroid={centroid:.0f}Hz)")
        elif 5 < duration < 60 and centroid < AIRCRAFT_CENTROID_HZ:
            return ("aircraft_passage", 0.55,
                    f"Low-frequency passage pattern (centroid={centroid:.0f}Hz)")

    # Bats: energy centred above the audible range. Checked before the diel
    # rules because echolocation is unambiguous from its band alone — no bird,
    # frog or engine puts its dominant energy above 16 kHz.
    if is_bat_band(dominant_band):
        if duration > INSECT_CHORUS_MIN_DURATION_S:
            return ("insect_chorus", 0.6,
                    f"Sustained energy in {dominant_band} for {duration:.0f}s - "
                    f"too long for echolocation; high-frequency insect chorus")
        if duration <= BAT_PASS_MAX_DURATION_S:
            return ("bat_echolocation", 0.5,
                    f"Brief ultrasonic event in {dominant_band} "
                    f"(centroid={centroid:.0f}Hz) - candidate bat pass, but the "
                    f"same band carries katydids; verify before trusting")
        return ("insect_chorus", 0.4,
                f"Ultrasonic energy of intermediate duration ({duration:.0f}s) "
                f"in {dominant_band}")

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
        if dominant_band == "biophony_low" and flatness < TONAL_FLATNESS:
            return ("amphibian_assembly", 0.7,
                    f"Low-frequency tonal signals at night (flatness={flatness:.2f})")
        if is_high_band(dominant_band):
            return ("nocturnal_voice", 0.65,
                    f"High-frequency nocturnal activity")
        if dominant_band == "biophony_mid":
            return ("nocturnal_voice", 0.6,
                    f"Mid-frequency nocturnal activity")

    # Insect chorus: high frequency, high flatness, sustained
    if is_high_band(dominant_band) and duration > 10:
        return ("insect_chorus", 0.7,
                f"Sustained high-frequency activity (band={dominant_band})")

    # Amphibian assembly: low biophony, tonal, often sustained
    if (dominant_band == "biophony_low" and flatness < TONAL_FLATNESS
            and duration > 5):
        return ("amphibian_assembly", 0.65,
                f"Tonal low-frequency sustained activity")

    # Alarm/alert: short, high flux, mid-frequency
    if duration < 5 and peak_flux > 0 and dominant_band == "biophony_mid":
        return ("alarm_or_alert", 0.5,
                f"Short, intense mid-frequency event")

    # Territorial: mid-frequency, moderate duration, tonal
    if (dominant_band == "biophony_mid" and flatness < TERRITORIAL_FLATNESS
            and 2 < duration < 30):
        return ("territorial_announcement", 0.55,
                f"Tonal mid-frequency vocalization")

    # Community shift: multiple bands active
    active_bands = sum(1 for v in band_energies.values() if v > 0)
    if (active_bands >= COMMUNITY_SHIFT_BANDS
            and dominant_ratio < COMMUNITY_SHIFT_DOMINANCE):
        return ("community_shift", 0.45,
                f"Energy spread across {active_bands} bands")

    # Default: classify by dominant band
    if dominant_band in ("biophony_mid", "biophony_low"):
        return ("territorial_announcement", 0.3,
                f"Unspecified biophonic event in {dominant_band}")
    if is_high_band(dominant_band):
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
