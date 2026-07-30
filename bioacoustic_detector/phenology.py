"""
Phenological calendar from cross-recording acoustic analysis.

Tracks how acoustic communities shift across hours, days, and seasons:
- Diel cycle (24h): dawn chorus onset, dusk transition, nocturnal peaks
- Multi-day: community stability, arrival/departure of vocal groups
- Seasonal: biophonic richness shifts, breeding chorus, rain transitions

The calendar is the toolkit's primary product. Everything here is shaped so it
can leave the machine as OSC: each day becomes a frame of scalars, and every
scalar also gets a 0..1 companion in `cv` that maps straight onto a control
voltage, a laser parameter, or a synthesis argument. See osc_output.py.
"""

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

from .config import PhenologyConfig

# Fields exposed per day, and the OSC/CV names they normalize to
CV_FIELDS = (
    "activity",    # events per recording
    "richness",    # distinct ecological roles
    "biophony",    # share of biophonic events
    "geophony",    # share of geophonic events
    "anthrophony",  # share of anthrophonic events
    "ndsi",        # soundscape index (bipolar source, normalized)
    "adi",         # acoustic diversity
    "aci",         # acoustic complexity
    "dawn",        # dawn chorus onset, minutes after midnight
)


def build_phenological_calendar(recordings: list[dict],
                                config: PhenologyConfig | None = None) -> dict:
    """
    Build a phenological calendar from multiple recording results.

    Each recording dict should contain:
        - datetime: recording datetime
        - events: list of event dicts with classification info
        - indices: dict of ecoacoustic indices
        - band_energies: dict of band -> mean energy

    Returns a calendar dict with:
        - diel_pattern: 24-hour activity profile
        - diel_table: 24 normalized values, ready to send as an OSC wavetable
        - daily_entries: per-day summaries (incl. per-hour event counts)
        - phenological_events: detected long-term acoustic shifts
        - dawn_chorus_times: dawn chorus onset per day
        - frames: per-day OSC frames with normalized `cv` values
        - ranges: the min/max used for normalization
    """
    config = config or PhenologyConfig()
    empty = {"diel_pattern": {}, "diel_table": [0.0] * 24, "daily_entries": [],
             "phenological_events": [], "dawn_chorus_times": [],
             "frames": [], "ranges": {}}

    if not recordings:
        return empty

    recs = sorted([r for r in recordings if r.get("datetime")],
                  key=lambda r: r["datetime"])
    if not recs:
        return empty

    diel = _compute_diel_pattern(recs)
    daily = _compute_daily_entries(recs)
    dawn_times = _detect_dawn_chorus_times(recs)
    pheno_events = _detect_phenological_events(daily, dawn_times, config)
    frames, ranges = build_osc_frames(daily, dawn_times, config)

    return {
        "diel_pattern": diel,
        "diel_table": _diel_table(diel),
        "daily_entries": daily,
        "phenological_events": pheno_events,
        "dawn_chorus_times": dawn_times,
        "frames": frames,
        "ranges": ranges,
    }


def _compute_diel_pattern(recs: list[dict]) -> dict:
    """Compute 24-hour acoustic activity profile."""
    hourly_activity = defaultdict(list)
    hourly_domains = defaultdict(lambda: defaultdict(int))

    for r in recs:
        dt = r["datetime"]
        hour = dt.hour
        events = r.get("events", [])
        hourly_activity[hour].append(len(events))

        for e in events:
            domain = e.get("domain", "unknown")
            hourly_domains[hour][domain] += 1

    pattern = {}
    for hour in range(24):
        counts = hourly_activity.get(hour, [0])
        domains = dict(hourly_domains.get(hour, {}))
        pattern[hour] = {
            "mean_events": float(np.mean(counts)) if counts else 0,
            "max_events": int(max(counts)) if counts else 0,
            "n_recordings": len(hourly_activity.get(hour, [])),
            "domain_counts": domains,
        }

    return pattern


def _diel_table(diel: dict) -> list[float]:
    """24 values in 0..1 — a diel activity wavetable for OSC consumers."""
    means = [float(diel.get(h, {}).get("mean_events", 0.0)) for h in range(24)]
    peak = max(means) if means else 0.0
    if peak <= 0:
        return [0.0] * 24
    return [round(v / peak, 4) for v in means]


def _compute_daily_entries(recs: list[dict]) -> list[dict]:
    """Compute per-day summaries, including a per-hour event histogram."""
    by_day = defaultdict(list)
    for r in recs:
        day_key = r["datetime"].strftime("%Y-%m-%d")
        by_day[day_key].append(r)

    entries = []
    for day_str, day_recs in sorted(by_day.items()):
        all_events = []
        band_totals = defaultdict(float)
        indices_sum = defaultdict(list)
        hourly = defaultdict(int)

        for r in day_recs:
            events = r.get("events", [])
            all_events.extend(events)
            hourly[r["datetime"].hour] += len(events)
            for band, energy in r.get("band_energies", {}).items():
                band_totals[band] += energy
            for idx_name, idx_val in r.get("indices", {}).items():
                indices_sum[idx_name].append(idx_val)

        domain_counts = defaultdict(int)
        role_counts = defaultdict(int)
        for e in all_events:
            domain_counts[e.get("domain", "unknown")] += 1
            role_counts[e.get("role", "unknown")] += 1

        mean_indices = {k: float(np.mean(v)) for k, v in indices_sum.items()}
        n_events = len(all_events)

        entries.append({
            "date": day_str,
            "day_of_year": datetime.strptime(day_str, "%Y-%m-%d").timetuple().tm_yday,
            "n_recordings": len(day_recs),
            "n_events": n_events,
            "events_per_recording": round(n_events / max(len(day_recs), 1), 3),
            "richness": len(role_counts),
            "domain_counts": dict(domain_counts),
            "domain_shares": {d: round(c / n_events, 4)
                              for d, c in domain_counts.items()} if n_events else {},
            "role_counts": dict(role_counts),
            "band_energies": dict(band_totals),
            "mean_indices": mean_indices,
            "hourly_events": {h: hourly.get(h, 0) for h in range(24)},
        })

    return entries


def _detect_dawn_chorus_times(recs: list[dict]) -> list[dict]:
    """
    Detect dawn chorus onset time per day.

    Looks for the first biophonic event between 3:00-8:00 each day.
    Returns list of {date, onset_minutes} where onset_minutes is
    minutes after midnight.
    """
    by_day = defaultdict(list)
    for r in recs:
        dt = r["datetime"]
        day_key = dt.strftime("%Y-%m-%d")
        for e in r.get("events", []):
            if e.get("domain") == "biophony":
                event_hour = dt.hour + e.get("onset_s", 0) / 3600
                if 3 <= event_hour <= 8:
                    minutes = dt.hour * 60 + dt.minute + e.get("onset_s", 0) / 60
                    by_day[day_key].append(minutes)

    results = []
    for day, times in sorted(by_day.items()):
        if times:
            results.append({
                "date": day,
                "onset_minutes": round(min(times), 1),
                "day_of_year": datetime.strptime(day, "%Y-%m-%d").timetuple().tm_yday,
            })

    return results


def _detect_phenological_events(daily: list[dict], dawn_times: list[dict],
                                config: PhenologyConfig | None = None) -> list[dict]:
    """
    Detect long-term phenological events from daily summaries.

    Types:
    - breeding_chorus_onset: biophony_low + biophony_high energy increase
    - migration_acoustic_shift: ADI change > threshold across days
    - rain_season_transition: geophony rain events increase
    - dawn_chorus_advance_delay: dawn chorus onset time shifts
    """
    config = config or PhenologyConfig()
    events = []

    if len(daily) < 2:
        return events

    for i in range(1, len(daily)):
        prev, curr = daily[i - 1], daily[i]

        # Breeding chorus onset: low + high biophony energy both jump
        prev_low = prev.get("band_energies", {}).get("biophony_low", 0)
        curr_low = curr.get("band_energies", {}).get("biophony_low", 0)
        prev_high = prev.get("band_energies", {}).get("biophony_high", 0)
        curr_high = curr.get("band_energies", {}).get("biophony_high", 0)

        if prev_low > 0 and prev_high > 0:
            low_ratio = curr_low / max(prev_low, 1e-10)
            high_ratio = curr_high / max(prev_high, 1e-10)
            if (low_ratio > config.breeding_energy_ratio
                    and high_ratio > config.breeding_energy_ratio):
                events.append({
                    "type": "breeding_chorus_onset",
                    "date": curr["date"],
                    "day_of_year": curr["day_of_year"],
                    "magnitude": round(min(low_ratio, high_ratio), 3),
                    "description": (f"Biophony low ({low_ratio:.1f}x) and high "
                                    f"({high_ratio:.1f}x) energy increased"),
                })

        # Niche turnover (migration indicator)
        prev_adi = prev.get("mean_indices", {}).get("adi", 0)
        curr_adi = curr.get("mean_indices", {}).get("adi", 0)
        if abs(curr_adi - prev_adi) > config.adi_shift:
            events.append({
                "type": "migration_acoustic_shift",
                "date": curr["date"],
                "day_of_year": curr["day_of_year"],
                "magnitude": round(abs(curr_adi - prev_adi), 3),
                "description": f"ADI shifted from {prev_adi:.2f} to {curr_adi:.2f}",
            })

        # Rain season transition
        prev_geo = prev.get("domain_counts", {}).get("geophony", 0)
        curr_geo = curr.get("domain_counts", {}).get("geophony", 0)
        if curr_geo > prev_geo + config.geophony_event_jump:
            events.append({
                "type": "rain_season_transition",
                "date": curr["date"],
                "day_of_year": curr["day_of_year"],
                "magnitude": float(curr_geo - prev_geo),
                "description": f"Geophonic events increased from {prev_geo} to {curr_geo}",
            })

        # Nocturnal community change: night-active roles turn over
        prev_roles = set(prev.get("role_counts", {}))
        curr_roles = set(curr.get("role_counts", {}))
        nocturnal = {"nocturnal_voice", "amphibian_assembly", "insect_chorus"}
        gained = (curr_roles - prev_roles) & nocturnal
        lost = (prev_roles - curr_roles) & nocturnal
        if gained or lost:
            changes = ([f"+{r}" for r in sorted(gained)]
                       + [f"-{r}" for r in sorted(lost)])
            events.append({
                "type": "nocturnal_community_change",
                "date": curr["date"],
                "day_of_year": curr["day_of_year"],
                "magnitude": float(len(gained) + len(lost)),
                "description": "Night assemblage changed: " + ", ".join(changes),
            })

    # Dawn chorus timing shift
    for i in range(1, len(dawn_times)):
        shift = dawn_times[i]["onset_minutes"] - dawn_times[i - 1]["onset_minutes"]
        if abs(shift) > config.dawn_shift_minutes:
            direction = "advanced" if shift < 0 else "delayed"
            events.append({
                "type": "dawn_chorus_advance_delay",
                "date": dawn_times[i]["date"],
                "day_of_year": dawn_times[i]["day_of_year"],
                "magnitude": round(shift, 1),
                "description": f"Dawn chorus {direction} by {abs(shift):.0f} minutes",
            })

    events.sort(key=lambda e: (e["date"], e["type"]))
    return events


# --- OSC-facing shaping -----------------------------------------------------

def build_osc_frames(daily: list[dict], dawn_times: list[dict],
                     config: PhenologyConfig | None = None
                     ) -> tuple[list[dict], dict]:
    """
    Turn daily summaries into per-day OSC frames.

    Each frame carries raw values (for analysis) and a `cv` block scaled to
    0..1 across the whole dataset (for instruments). Normalization ranges are
    returned alongside so a receiver can reproduce or invert the mapping.
    """
    config = config or PhenologyConfig()
    if not daily:
        return [], {}

    dawn_by_date = {d["date"]: d["onset_minutes"] for d in dawn_times}

    raw = []
    for entry in daily:
        indices = entry.get("mean_indices", {})
        shares = entry.get("domain_shares", {})
        raw.append({
            "date": entry["date"],
            "day_of_year": entry["day_of_year"],
            "n_recordings": entry["n_recordings"],
            "n_events": entry["n_events"],
            "activity": entry["events_per_recording"],
            "richness": float(entry["richness"]),
            "biophony": float(shares.get("biophony", 0.0)),
            "geophony": float(shares.get("geophony", 0.0)),
            "anthrophony": float(shares.get("anthrophony", 0.0)),
            "ndsi": float(indices.get("ndsi", 0.0)),
            "adi": float(indices.get("adi", 0.0)),
            "aci": float(indices.get("aci", 0.0)),
            "dawn": dawn_by_date.get(entry["date"]),
            "dominant_role": _dominant_role(entry),
            "role_counts": entry.get("role_counts", {}),
            "hourly_events": entry.get("hourly_events", {}),
        })

    ranges = {}
    for field in CV_FIELDS:
        values = [r[field] for r in raw if r.get(field) is not None]
        if not values:
            ranges[field] = {"min": 0.0, "max": 0.0}
            continue
        lo, hi = float(min(values)), float(max(values))
        # Shares and NDSI have meaningful fixed ranges; keep them absolute
        if field in ("biophony", "geophony", "anthrophony"):
            lo, hi = 0.0, 1.0
        elif field == "ndsi":
            lo, hi = -1.0, 1.0
        ranges[field] = {"min": lo, "max": hi}

    if not config.normalize_for_cv:
        return raw, ranges

    for frame in raw:
        cv = {}
        for field in CV_FIELDS:
            value = frame.get(field)
            span = ranges[field]
            if value is None:
                cv[field] = 0.0
                continue
            width = span["max"] - span["min"]
            cv[field] = round((value - span["min"]) / width, 4) if width > 0 else 0.0
        frame["cv"] = cv

    return raw, ranges


def _dominant_role(entry: dict) -> str:
    roles = entry.get("role_counts", {})
    if not roles:
        return "silence"
    return max(roles, key=roles.get)


def write_phenology_csv(calendar: dict, output_path: str) -> str:
    """Write a tidy one-row-per-day CSV of the phenological series."""
    frames = calendar.get("frames", [])
    if not frames:
        Path(output_path).write_text("", encoding="utf-8")
        return output_path

    columns = ["date", "day_of_year", "n_recordings", "n_events", "activity",
               "richness", "biophony", "geophony", "anthrophony",
               "ndsi", "adi", "aci", "dawn", "dominant_role"]
    cv_columns = [f"cv_{f}" for f in CV_FIELDS]

    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns + cv_columns)
        for frame in frames:
            cv = frame.get("cv", {})
            writer.writerow(
                [frame.get(c, "") if frame.get(c) is not None else ""
                 for c in columns]
                + [cv.get(f, "") for f in CV_FIELDS]
            )

    return output_path


def generate_phenology_html(calendar: dict, output_path: str) -> str:
    """
    Generate an HTML phenological calendar visualization.
    Heatmap: days x hours, colored by actual per-day acoustic activity.
    """
    pheno_events = calendar.get("phenological_events", [])
    frames = calendar.get("frames", [])

    heatmap_json = json.dumps(_build_heatmap_data(calendar))
    dawn_json = json.dumps(calendar.get("dawn_chorus_times", []))
    series_json = json.dumps(_build_series_data(frames))
    diel_json = json.dumps(calendar.get("diel_table", []))

    events_html = "".join(
        f'<div class="pheno-event">'
        f'<span class="pheno-type">{e["type"].replace("_", " ")}</span> '
        f'<span class="pheno-date">{e["date"]}</span>'
        f'<p>{e["description"]}</p></div>'
        for e in pheno_events
    ) or ('<p style="color:#7f8c8d">No phenological events detected '
          '(requires multiple recording days)</p>')

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Phenological Calendar</title>
    <script src="https://cdn.plot.ly/plotly-3.3.0.min.js" charset="utf-8"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh; padding: 20px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{
            color: white; text-align: center; margin-bottom: 25px;
            font-size: 2.2em; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        .panel {{
            background: white; padding: 20px; border-radius: 12px;
            margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .panel h2 {{ color: #2c3e50; margin-bottom: 15px; }}
        .pheno-event {{
            padding: 10px; margin: 8px 0; border-radius: 6px;
            border-left: 4px solid #667eea; background: #f8f9fa;
        }}
        .pheno-type {{
            font-weight: 600; color: #2c3e50; text-transform: capitalize;
        }}
        .pheno-date {{ color: #7f8c8d; font-size: 13px; }}
        footer {{
            margin-top: 30px; text-align: center; color: white; font-size: 13px;
        }}
    </style>
</head>
<body>
<div class="container">
    <h1>Phenological Calendar</h1>

    <div class="panel">
        <h2>Diel Activity Heatmap</h2>
        <div id="heatmap" style="min-height:400px;"></div>
    </div>

    <div class="panel">
        <h2>Phenological Series (OSC control values)</h2>
        <div id="series-chart" style="min-height:340px;"></div>
    </div>

    <div class="panel">
        <h2>Dawn Chorus Timing</h2>
        <div id="dawn-chart" style="min-height:300px;"></div>
    </div>

    <div class="panel">
        <h2>24h Activity Wavetable</h2>
        <div id="diel-chart" style="min-height:260px;"></div>
    </div>

    <div class="panel">
        <h2>Phenological Events</h2>
        <div id="pheno-events">{events_html}</div>
    </div>

    <footer>Phenological Calendar — Bioacoustic toolkit</footer>
</div>

<script>
var LAYOUT = {{
    margin: {{ t: 40, b: 55, l: 70, r: 20 }},
    paper_bgcolor: 'transparent',
    font: {{ family: 'Segoe UI' }}
}};
function layout(extra) {{ return Object.assign({{}}, LAYOUT, extra); }}

var hmData = {heatmap_json};
if (hmData.z.length > 0) {{
    Plotly.newPlot('heatmap', [{{
        z: hmData.z, x: hmData.x, y: hmData.y,
        type: 'heatmap', colorscale: 'YlOrRd',
        colorbar: {{ title: 'Events' }}
    }}], layout({{
        title: 'Acoustic Activity (Days x Hours)',
        xaxis: {{ title: 'Hour of Day', dtick: 1 }},
        yaxis: {{ title: 'Date' }}
    }}), {{ responsive: true }});
}}

var series = {series_json};
if (series.dates.length > 0) {{
    Plotly.newPlot('series-chart', series.traces, layout({{
        title: 'Normalized daily control values (0-1)',
        xaxis: {{ title: 'Date' }},
        yaxis: {{ title: 'CV', range: [0, 1] }}
    }}), {{ responsive: true }});
}}

var dawnData = {dawn_json};
if (dawnData.length > 0) {{
    Plotly.newPlot('dawn-chart', [{{
        x: dawnData.map(d => d.date),
        y: dawnData.map(d => d.onset_minutes),
        type: 'scatter', mode: 'lines+markers',
        line: {{ color: '#f39c12', width: 2 }},
        marker: {{ size: 8, color: '#e67e22' }},
        name: 'Dawn Chorus Onset'
    }}], layout({{
        title: 'Dawn Chorus Onset Time',
        xaxis: {{ title: 'Date' }},
        yaxis: {{ title: 'Minutes after midnight' }}
    }}), {{ responsive: true }});
}}

var diel = {diel_json};
if (diel.length > 0) {{
    Plotly.newPlot('diel-chart', [{{
        x: Array.from({{length: 24}}, (_, i) => i), y: diel,
        type: 'bar', marker: {{ color: '#667eea' }}, name: 'Activity'
    }}], layout({{
        title: 'Sent as /phenology/diel/table (24 floats, 0-1)',
        xaxis: {{ title: 'Hour', dtick: 1 }},
        yaxis: {{ title: 'Normalized activity', range: [0, 1] }}
    }}), {{ responsive: true }});
}}
</script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    return output_path


def _build_heatmap_data(calendar: dict) -> dict:
    """Build heatmap data: one row per day, one column per hour."""
    daily = calendar.get("daily_entries", [])
    if not daily:
        return {"z": [], "x": [], "y": []}

    hours = list(range(24))
    z = []
    for entry in daily:
        hourly = entry.get("hourly_events", {})
        # JSON round-trips turn the int hour keys into strings
        z.append([float(hourly.get(h, hourly.get(str(h), 0))) for h in hours])

    return {"z": z, "x": hours, "y": [d["date"] for d in daily]}


def _build_series_data(frames: list[dict]) -> dict:
    """Plotly traces for the normalized daily control values."""
    if not frames:
        return {"dates": [], "traces": []}

    dates = [f["date"] for f in frames]
    shown = ("activity", "richness", "biophony", "geophony", "ndsi", "adi")
    traces = [{
        "x": dates,
        "y": [f.get("cv", {}).get(field, 0.0) for f in frames],
        "name": field,
        "type": "scatter",
        "mode": "lines+markers",
    } for field in shown]

    return {"dates": dates, "traces": traces}
