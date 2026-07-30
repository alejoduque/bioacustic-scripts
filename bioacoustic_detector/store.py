"""
Reading detection output back off disk.

`events.json` is the toolkit's interchange format. Writing it once and reading
it back lets the expensive step (spectral analysis) happen once while the cheap
steps — phenology, gallery, OSC export, streaming — can be re-run, re-tuned and
re-shaped as often as needed.
"""

import json
from datetime import datetime
from pathlib import Path

RESULT_FILENAME = "events.json"
CALENDAR_FILENAME = "phenological_calendar.json"


MEDIA_KEYS = ("clip_path", "video_path", "poster_path", "thumbnail_path",
              "gif_path")


def result_to_json(result: dict, base: str = "") -> dict:
    """
    Serializable form of an in-memory result dict.

    When `base` is given, media paths are stored relative to it so the output
    tree stays valid after being moved, copied or published.
    """
    dt = result.get("datetime")
    events = result.get("events", [])
    if base:
        events = [
            {**event,
             **{k: relativize(event[k], base) for k in MEDIA_KEYS if event.get(k)}}
            for event in events
        ]
        reels = {role: relativize(path, base)
                 for role, path in (result.get("reels") or {}).items()}
    else:
        reels = result.get("reels", {})

    return {
        "filename": result.get("filename", ""),
        "filepath": result.get("filepath", ""),
        "recording_datetime": dt.isoformat() if dt else None,
        "duration_s": result.get("duration_s"),
        "sample_rate": result.get("sample_rate"),
        "habitat": result.get("habitat", ""),
        "season": result.get("season", ""),
        "temperature_c": result.get("temperature_c"),
        "indices": result.get("indices", {}),
        "band_energies": result.get("band_energies", {}),
        "parliament": result.get("parliament", {}),
        "n_events": result.get("n_events", 0),
        "n_clips": result.get("n_clips", 0),
        "events": events,
        # Informational only — readers use the file's own location instead, so
        # the tree survives being moved or produced from another directory.
        "output_dir": Path(result.get("output_dir", "")).name,
        "report_path": Path(result.get("report_path", "")).name,
        "reels": reels,
    }


def write_result(result: dict, output_dir: str) -> str:
    """Write one recording's result as events.json, with portable media paths."""
    path = Path(output_dir) / RESULT_FILENAME
    path.write_text(
        json.dumps(result_to_json(result, base=output_dir), indent=2, default=str),
        encoding="utf-8",
    )
    return str(path)


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def read_result(path: str) -> dict:
    """Read one events.json back into an in-memory result dict."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    result = dict(data)
    result["datetime"] = _parse_dt(data.get("recording_datetime"))
    result["ndsi"] = data.get("indices", {}).get("ndsi", 0)
    # Always trust where the file actually is over the path recorded inside it:
    # detection may have run from a different working directory, or the whole
    # tree may have been moved.
    result["output_dir"] = str(Path(path).resolve().parent)

    # Media paths are stored relative to the recording's own output dir so the
    # tree can be moved or published wholesale.
    base = Path(result["output_dir"])
    for event in result.get("events", []):
        for key in MEDIA_KEYS:
            value = event.get(key)
            if value and not Path(value).is_absolute():
                event[key] = str(base / value)
    if result.get("report_path") and not Path(result["report_path"]).is_absolute():
        result["report_path"] = str(base / result["report_path"])
    result["reels"] = {
        role: (str(base / p) if not Path(p).is_absolute() else p)
        for role, p in (data.get("reels") or {}).items()
    }
    return result


def load_results(output_dir: str) -> list[dict]:
    """
    Load every events.json under an output directory, oldest recording first.

    Accepts either the batch output directory or a single recording's directory.
    """
    root = Path(output_dir)
    if not root.exists():
        raise FileNotFoundError(f"No such directory: {output_dir}")

    paths = sorted(root.glob(f"*/{RESULT_FILENAME}"))
    if not paths and (root / RESULT_FILENAME).is_file():
        paths = [root / RESULT_FILENAME]
    if not paths:
        paths = sorted(root.glob(f"**/{RESULT_FILENAME}"))

    results = [read_result(str(p)) for p in paths]
    results.sort(key=lambda r: (r.get("datetime") is None,
                                r.get("datetime") or datetime.min))
    return results


def find_calendar(output_dir: str) -> str:
    """Path to the phenological calendar in an output dir, or "" if absent."""
    direct = Path(output_dir) / CALENDAR_FILENAME
    if direct.is_file():
        return str(direct)
    found = sorted(Path(output_dir).glob(f"**/{CALENDAR_FILENAME}"))
    return str(found[0]) if found else ""


def relativize(path: str, base: str) -> str:
    """Path relative to base when possible, for portable events.json."""
    if not path:
        return ""
    try:
        return str(Path(path).resolve().relative_to(Path(base).resolve()))
    except ValueError:
        return path
