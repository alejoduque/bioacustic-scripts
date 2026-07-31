"""
Deployment stations: coordinates, elevation, land cover and locality.

The recorder writes time, temperature and its own id into the WAV header, but it
does not know where it was. That lives in the survey's GIS layer — a KML or
shapefile of sampling points — and without it a clip cannot be placed on a map
or grouped by anything other than the folder it came from.

Reads a KML export (the `<SimpleData>` attribute table Google Earth and QGIS
both write) and matches a recording to its station by land cover and date.

    stations = load_stations("Ubicacion/KML/AudioMoth.kml")
    site = match_station(stations, habitat="Bosque de galería y-o ripario",
                         when=datetime(2024, 7, 27))

Nothing else in the toolkit requires this: with no station table the extra
fields are simply absent from the output.
"""

import re
import unicodedata
from datetime import datetime
from pathlib import Path

# Attribute names in the La Luna survey layer. Other surveys will differ, which
# is why they are named here rather than assumed throughout the code.
FIELD_STATION = "ID_MUES_PT"
FIELD_COVER = "N_COBERT"
FIELD_LOCALITY = "VEREDA"
FIELD_ELEVATION = "COTA"
FIELD_CORINE = "NOMENCLAT"
FIELD_HABITAT = "HABITAT"
FIELD_SAMPLED = "FEC_MUEST"
FIELD_PROJECT = "PROYECTO"


def normalize_cover(name: str) -> str:
    """
    Reduce a land-cover name to a form that survives being a directory name.

    A filesystem cannot hold "Bosque de galería y/o ripario", so the survey's
    slash becomes a hyphen on disk and the two spellings no longer compare
    equal. Accents, case and singular/plural drift the same way ("Palma de
    aceite" in the GIS layer, "Palmas de aceite" in one season's folder).
    """
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[/\-_]+", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\b(y o|yo)\b", " ", text)          # "y/o" -> nothing
    text = re.sub(r"(\w+)s\b", r"\1", text)            # crude de-pluralisation
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(value: str):
    for fmt in ("%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except (ValueError, TypeError):
            continue
    return None


def load_stations(kml_path: str) -> list[dict]:
    """
    Parse stations out of a KML export.

    Returns one dict per placemark: every `<SimpleData>` attribute, plus `lat`,
    `lon` and a parsed `sampled_at`. Placemarks without coordinates are skipped.
    """
    text = Path(kml_path).read_text(encoding="utf-8", errors="replace")
    stations = []

    for block in re.findall(r"<Placemark[^>]*>(.*?)</Placemark>", text, re.S):
        row = {k: v.strip() for k, v in
               re.findall(r'<SimpleData name="([^"]+)">(.*?)</SimpleData>',
                          block, re.S)}
        coord = re.search(r"<coordinates>\s*([-0-9.]+),([-0-9.]+)", block)
        if not coord:
            continue
        row["lon"] = float(coord.group(1))
        row["lat"] = float(coord.group(2))
        row["sampled_at"] = _parse_date(row.get(FIELD_SAMPLED, ""))
        row["cover_key"] = normalize_cover(row.get(FIELD_COVER, ""))
        stations.append(row)

    return stations


def match_station(stations: list[dict], habitat: str,
                  when: datetime | None = None) -> dict | None:
    """
    Find the station a recording belongs to.

    Matches on normalised land cover. Surveys typically place one station per
    cover per campaign, so when several match, the one sampled nearest the
    recording date wins — which is what separates a rainy-season station from
    the dry-season station in the same cover.
    """
    if not stations or not habitat:
        return None

    key = normalize_cover(habitat)
    candidates = [s for s in stations if s.get("cover_key") == key]
    if not candidates:
        return None
    if len(candidates) == 1 or when is None:
        return candidates[0]

    dated = [s for s in candidates if s.get("sampled_at")]
    if not dated:
        return candidates[0]
    return min(dated, key=lambda s: abs((s["sampled_at"] - when).total_seconds()))


def station_fields(station: dict | None) -> dict:
    """Flatten a station into the fields carried on every event record."""
    if not station:
        return {}
    try:
        elevation = round(float(station.get(FIELD_ELEVATION, "") or 0), 1)
    except ValueError:
        elevation = None
    return {
        "station_id": station.get(FIELD_STATION, ""),
        "latitude": round(station["lat"], 6),
        "longitude": round(station["lon"], 6),
        "elevation_m": elevation,
        "locality": station.get(FIELD_LOCALITY, ""),
        "corine_code": station.get(FIELD_CORINE, ""),
        "habitat_description": station.get(FIELD_HABITAT, ""),
        "project": station.get(FIELD_PROJECT, ""),
    }


def find_station_table(start: str) -> str:
    """
    Look for a station KML near the recordings, walking upward.

    Survey layers usually sit beside the audio rather than inside it, so a
    recording several folders deep still finds `Ubicacion/KML/AudioMoth.kml`
    at the campaign root.
    """
    here = Path(start).resolve()
    if here.is_file():
        here = here.parent
    for parent in [here, *here.parents][:8]:
        for pattern in ("Ubicacion/KML/*.kml", "*.kml", "**/AudioMoth.kml"):
            found = sorted(parent.glob(pattern))
            if found:
                return str(found[0])
    return ""
