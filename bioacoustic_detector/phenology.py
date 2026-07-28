"""
Phenological calendar from cross-recording acoustic analysis.

Tracks how acoustic communities shift across hours, days, and seasons:
- Diel cycle (24h): dawn chorus onset, dusk transition, nocturnal peaks
- Multi-day: community stability, arrival/departure of vocal groups
- Seasonal: biophonic richness shifts, breeding chorus, rain transitions
"""

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np


def build_phenological_calendar(recordings: list[dict]) -> dict:
    """
    Build a phenological calendar from multiple recording results.

    Each recording dict should contain:
        - datetime: recording datetime
        - events: list of event dicts with classification info
        - indices: dict of ecoacoustic indices
        - band_energies: dict of band -> mean energy

    Returns a phenological calendar dict with:
        - diel_pattern: 24-hour activity profile
        - daily_entries: per-day summaries
        - phenological_events: detected long-term acoustic shifts
        - dawn_chorus_times: dawn chorus onset per day
    """
    if not recordings:
        return {"diel_pattern": {}, "daily_entries": [],
                "phenological_events": [], "dawn_chorus_times": []}

    # Sort by datetime
    recs = sorted([r for r in recordings if r.get("datetime")],
                  key=lambda r: r["datetime"])

    if not recs:
        return {"diel_pattern": {}, "daily_entries": [],
                "phenological_events": [], "dawn_chorus_times": []}

    diel = _compute_diel_pattern(recs)
    daily = _compute_daily_entries(recs)
    dawn_times = _detect_dawn_chorus_times(recs)
    pheno_events = _detect_phenological_events(daily, dawn_times)

    return {
        "diel_pattern": diel,
        "daily_entries": daily,
        "phenological_events": pheno_events,
        "dawn_chorus_times": dawn_times,
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
            "n_recordings": len(counts),
            "domain_counts": domains,
        }

    return pattern


def _compute_daily_entries(recs: list[dict]) -> list[dict]:
    """Compute per-day summaries."""
    by_day = defaultdict(list)
    for r in recs:
        day_key = r["datetime"].strftime("%Y-%m-%d")
        by_day[day_key].append(r)

    entries = []
    for day_str, day_recs in sorted(by_day.items()):
        all_events = []
        band_totals = defaultdict(float)
        indices_sum = defaultdict(list)

        for r in day_recs:
            all_events.extend(r.get("events", []))
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

        entries.append({
            "date": day_str,
            "day_of_year": datetime.strptime(day_str, "%Y-%m-%d").timetuple().tm_yday,
            "n_recordings": len(day_recs),
            "n_events": len(all_events),
            "domain_counts": dict(domain_counts),
            "role_counts": dict(role_counts),
            "band_energies": dict(band_totals),
            "mean_indices": mean_indices,
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


def _detect_phenological_events(daily: list[dict],
                                dawn_times: list[dict]) -> list[dict]:
    """
    Detect long-term phenological events from daily summaries.

    Types:
    - breeding_chorus_onset: biophony_low + biophony_high energy increase
    - migration_acoustic_shift: ADI change > threshold across days
    - rain_season_transition: geophony rain events increase
    - dawn_chorus_advance_delay: dawn chorus onset time shifts
    - nocturnal_community_change: night assemblage shifts
    """
    events = []

    if len(daily) < 2:
        return events

    # Detect breeding chorus onset
    for i in range(1, len(daily)):
        prev_bio_low = daily[i-1].get("band_energies", {}).get("biophony_low", 0)
        curr_bio_low = daily[i].get("band_energies", {}).get("biophony_low", 0)
        prev_bio_high = daily[i-1].get("band_energies", {}).get("biophony_high", 0)
        curr_bio_high = daily[i].get("band_energies", {}).get("biophony_high", 0)

        if prev_bio_low > 0 and prev_bio_high > 0:
            low_ratio = curr_bio_low / max(prev_bio_low, 1e-10)
            high_ratio = curr_bio_high / max(prev_bio_high, 1e-10)
            if low_ratio > 2.0 and high_ratio > 2.0:
                events.append({
                    "type": "breeding_chorus_onset",
                    "date": daily[i]["date"],
                    "day_of_year": daily[i]["day_of_year"],
                    "description": f"Biophony low ({low_ratio:.1f}x) and high ({high_ratio:.1f}x) energy increased",
                })

    # Detect ADI shifts (migration indicator)
    for i in range(1, len(daily)):
        prev_adi = daily[i-1].get("mean_indices", {}).get("adi", 0)
        curr_adi = daily[i].get("mean_indices", {}).get("adi", 0)
        if abs(curr_adi - prev_adi) > 0.5:
            events.append({
                "type": "migration_acoustic_shift",
                "date": daily[i]["date"],
                "day_of_year": daily[i]["day_of_year"],
                "description": f"ADI shifted from {prev_adi:.2f} to {curr_adi:.2f}",
            })

    # Rain season transition
    for i in range(1, len(daily)):
        prev_geo = daily[i-1].get("domain_counts", {}).get("geophony", 0)
        curr_geo = daily[i].get("domain_counts", {}).get("geophony", 0)
        if curr_geo > prev_geo + 3:
            events.append({
                "type": "rain_season_transition",
                "date": daily[i]["date"],
                "day_of_year": daily[i]["day_of_year"],
                "description": f"Geophonic events increased from {prev_geo} to {curr_geo}",
            })

    # Dawn chorus timing shift
    if len(dawn_times) >= 2:
        for i in range(1, len(dawn_times)):
            shift = dawn_times[i]["onset_minutes"] - dawn_times[i-1]["onset_minutes"]
            if abs(shift) > 15:  # More than 15 minutes shift
                direction = "advanced" if shift < 0 else "delayed"
                events.append({
                    "type": "dawn_chorus_advance_delay",
                    "date": dawn_times[i]["date"],
                    "day_of_year": dawn_times[i]["day_of_year"],
                    "description": f"Dawn chorus {direction} by {abs(shift):.0f} minutes",
                })

    return events


def generate_phenology_html(calendar: dict, output_path: str) -> str:
    """
    Generate an HTML phenological calendar visualization.
    Heatmap: hours x days, colored by acoustic activity.
    """
    daily = calendar.get("daily_entries", [])
    dawn_times = calendar.get("dawn_chorus_times", [])
    pheno_events = calendar.get("phenological_events", [])

    # Build heatmap data
    heatmap_json = json.dumps(_build_heatmap_data(calendar))
    pheno_json = json.dumps(pheno_events)
    dawn_json = json.dumps(dawn_times)

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
            font-weight: 600; color: #2c3e50;
            text-transform: capitalize;
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
        <h2>Dawn Chorus Timing</h2>
        <div id="dawn-chart" style="min-height:300px;"></div>
    </div>

    <div class="panel">
        <h2>Phenological Events</h2>
        <div id="pheno-events">
            {"".join(
                f'<div class="pheno-event">'
                f'<span class="pheno-type">{e["type"].replace("_", " ")}</span> '
                f'<span class="pheno-date">{e["date"]}</span>'
                f'<p>{e["description"]}</p></div>'
                for e in pheno_events
            ) if pheno_events else '<p style="color:#7f8c8d">No phenological events detected (requires multiple recording days)</p>'}
        </div>
    </div>

    <footer>Phenological Calendar — Bioacoustic Event Detector v0.1.0</footer>
</div>

<script>
var hmData = {heatmap_json};
if (hmData.z.length > 0) {{
    Plotly.newPlot('heatmap', [{{
        z: hmData.z, x: hmData.x, y: hmData.y,
        type: 'heatmap', colorscale: 'YlOrRd',
        colorbar: {{ title: 'Events' }}
    }}], {{
        title: 'Acoustic Activity (Days x Hours)',
        xaxis: {{ title: 'Hour of Day', dtick: 1 }},
        yaxis: {{ title: 'Date' }},
        margin: {{ t: 40, b: 50, l: 100, r: 20 }},
        paper_bgcolor: 'transparent',
        font: {{ family: 'Segoe UI' }}
    }}, {{ responsive: true }});
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
    }}], {{
        title: 'Dawn Chorus Onset Time',
        xaxis: {{ title: 'Date' }},
        yaxis: {{ title: 'Minutes after midnight' }},
        margin: {{ t: 40, b: 50, l: 60, r: 20 }},
        paper_bgcolor: 'transparent',
        font: {{ family: 'Segoe UI' }}
    }}, {{ responsive: true }});
}}
</script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    return output_path


def _build_heatmap_data(calendar: dict) -> dict:
    """Build heatmap data: days x hours."""
    daily = calendar.get("daily_entries", [])
    diel = calendar.get("diel_pattern", {})

    if not daily:
        return {"z": [], "x": [], "y": []}

    dates = [d["date"] for d in daily]
    hours = list(range(24))

    # Build z matrix (days x hours)
    z = []
    for d in daily:
        row = []
        for h in hours:
            # Use diel pattern mean as fallback
            count = diel.get(h, {}).get("mean_events", 0)
            row.append(count)
        z.append(row)

    return {"z": z, "x": hours, "y": dates}
