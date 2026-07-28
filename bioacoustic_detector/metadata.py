"""
AudioMoth metadata extraction via metamoth + path-based habitat/season parsing.

Reuses the patterns from AudioMothRECS_LaLuna/audiomoth_processing.sh.
"""

from datetime import datetime
from pathlib import Path


KNOWN_COVERAGES = [
    "Bosque de galería y-o ripario",
    "Bosque denso alto de tierra firme",
    "Cultivos permanentes arbóreos",
    "Lagunas, lagos y ciénagas naturales",
    "Mosaico de cultivos",
    "Otros cultivos transitorios",
    "Palmas de aceite",
    "Pastos arbolados",
    "Pastos enmalezados",
    "Pastos limpios",
    "Plantación de latifoliadas",
    "Tierras desnudas y degradadas",
    "Vegetación secundaria alta",
    "Vegetación secundaria baja",
    "Zonas pantanosas",
]


def extract_location_from_path(filepath: str) -> dict:
    """Extract habitat, season, and site info from directory structure."""
    path = Path(filepath)
    parts = path.parts

    info = {"sitio": None, "epoca": None, "cobertura": None}

    for part in parts:
        if "Luna" in part or "Captiva" in part:
            info["sitio"] = "Luna Captiva"

        part_lower = part.lower()
        if "lluvia" in part_lower:
            info["epoca"] = "Época lluvias"
        elif "seca" in part_lower or "seco" in part_lower:
            info["epoca"] = "Época seca"

        for coverage in KNOWN_COVERAGES:
            if part == coverage:
                info["cobertura"] = coverage
                break

    if not info["cobertura"]:
        info["cobertura"] = path.parent.name

    return info


def parse_audiomoth_datetime(filename: str) -> datetime | None:
    """
    Parse datetime from AudioMoth filename (YYYYMMDD_HHMMSS.WAV).
    Returns None if pattern doesn't match.
    """
    stem = Path(filename).stem
    try:
        return datetime.strptime(stem, "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def get_recording_metadata(filepath: str) -> dict:
    """
    Extract full metadata for a recording.

    Tries metamoth first for AudioMoth-specific metadata,
    falls back to filename parsing.
    """
    location = extract_location_from_path(filepath)
    dt = parse_audiomoth_datetime(filepath)

    meta = {
        "filepath": str(filepath),
        "filename": Path(filepath).name,
        "datetime": dt,
        "habitat": location["cobertura"],
        "season": location["epoca"],
        "site": location["sitio"],
        "temperature_c": None,
        "battery_v": None,
        "audiomoth_id": None,
        "samplerate_hz": None,
        "duration_s": None,
    }

    # Try metamoth for richer metadata
    try:
        from metamoth import parse_metadata
        mm = parse_metadata(filepath)
        meta["datetime"] = getattr(mm, "datetime", dt) or dt
        meta["temperature_c"] = getattr(mm, "temperature_c", None)
        meta["battery_v"] = getattr(mm, "battery_state_v", None)
        meta["audiomoth_id"] = getattr(mm, "audiomoth_id", None)
        meta["samplerate_hz"] = getattr(mm, "samplerate_hz", None)
        meta["duration_s"] = getattr(mm, "duration_s", None)
    except Exception:
        pass

    return meta
