"""
HTML report generation with Plotly.js.

Matches the visual style from audiomoth_processing.sh:
gradient #667eea -> #764ba2, Plotly 3.3.0.
"""

import json
import os
from datetime import datetime
from pathlib import Path


def _href(path: str, base: Path) -> str:
    """Link from the report to a media file next to (or under) it."""
    if not path:
        return ""
    try:
        rel = os.path.relpath(Path(path).resolve(), base.resolve())
    except ValueError:
        rel = path
    return str(rel).replace(" ", "%20").replace("#", "%23")


def generate_event_report(source_file: str, events_data: list[dict],
                          parliament: dict, file_indices: dict,
                          recording_meta: dict, output_path: str) -> str:
    """
    Generate per-file HTML report with:
    - Parliament of the Living summary panel
    - Timeline visualization
    - Event cards with embedded video players
    - Acoustic indices charts
    """
    filename = Path(source_file).name
    base = Path(output_path).parent
    n_events = len(events_data)
    habitat = recording_meta.get("habitat", "Unknown")
    season = recording_meta.get("season", "Unknown")
    rec_dt = recording_meta.get("datetime")
    date_str = rec_dt.strftime("%d %B %Y %H:%M") if rec_dt else "Unknown"

    # Prepare Plotly data
    timeline_data = json.dumps(_build_timeline_data(events_data))
    pie_data = json.dumps(_build_pie_data(parliament))
    indices_data = json.dumps(_build_indices_data(events_data))
    flux_data = json.dumps(_build_flux_data(events_data))

    # Build event cards HTML
    event_cards = "\n".join(_event_card_html(e, i, base)
                            for i, e in enumerate(events_data, 1))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Parliament of the Living - {_escape(filename)}</title>
    <script src="https://cdn.plot.ly/plotly-3.3.0.min.js" charset="utf-8"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{
            color: white; text-align: center; margin-bottom: 10px;
            font-size: 2.2em; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        .subtitle {{
            color: rgba(255,255,255,0.85); text-align: center;
            margin-bottom: 25px; font-size: 1.1em;
        }}
        .panel {{
            background: white; padding: 20px; border-radius: 12px;
            margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .panel h2 {{
            color: #2c3e50; margin-bottom: 15px; font-size: 1.4em;
            border-bottom: 2px solid #667eea; padding-bottom: 8px;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
        }}
        .summary-item {{ text-align: center; }}
        .summary-label {{
            font-weight: 600; color: #7f8c8d; font-size: 11px;
            text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px;
        }}
        .summary-value {{
            color: #2c3e50; font-size: 28px; font-weight: bold;
        }}
        .charts-row {{
            display: grid; grid-template-columns: 1fr 1fr; gap: 20px;
        }}
        .chart-box {{ min-height: 350px; }}
        .event-card {{
            background: #f8f9fa; border-radius: 8px; padding: 15px;
            margin-bottom: 15px; border-left: 4px solid #667eea;
        }}
        .event-card.biophony {{ border-left-color: #27ae60; }}
        .event-card.geophony {{ border-left-color: #3498db; }}
        .event-card.anthrophony {{ border-left-color: #e74c3c; }}
        .event-card.transition {{ border-left-color: #f39c12; }}
        .event-header {{
            display: flex; justify-content: space-between;
            align-items: center; margin-bottom: 10px;
        }}
        .event-title {{ font-weight: 600; color: #2c3e50; font-size: 1.1em; }}
        .event-badge {{
            display: inline-block; padding: 3px 10px; border-radius: 12px;
            font-size: 11px; font-weight: 600; color: white;
        }}
        .badge-biophony {{ background: #27ae60; }}
        .badge-geophony {{ background: #3498db; }}
        .badge-anthrophony {{ background: #e74c3c; }}
        .badge-transition {{ background: #f39c12; }}
        .event-meta {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 8px; font-size: 13px; color: #555; margin-bottom: 10px;
        }}
        .event-meta span {{ font-weight: 500; color: #2c3e50; }}
        .event-why {{
            font-size: 12px; color: #7f8c8d; font-style: italic;
            margin-bottom: 8px;
        }}
        .event-links {{ margin-top: 8px; font-size: 12px; }}
        .event-links a {{ color: #667eea; text-decoration: none; margin-right: 10px; }}
        video {{
            width: 100%; max-width: 800px; border-radius: 8px;
            margin-top: 8px;
        }}
        footer {{
            margin-top: 30px; text-align: center; color: white;
            font-size: 13px; text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
        }}
        @media (max-width: 768px) {{
            .charts-row {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
<div class="container">
    <h1>Parliament of the Living</h1>
    <div class="subtitle">{_escape(filename)} | {_escape(habitat)} | {_escape(date_str)}</div>

    <!-- Parliament Summary -->
    <div class="panel">
        <h2>Acoustic Community</h2>
        <div class="summary-grid">
            <div class="summary-item">
                <div class="summary-label">Total Voices</div>
                <div class="summary-value">{parliament.get('total_voices', 0)}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Democracy Index</div>
                <div class="summary-value">{parliament.get('democracy_index', 0):.2f}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Niche Partitioning</div>
                <div class="summary-value">{parliament.get('niche_partitioning', 0):.2f}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Habitat</div>
                <div class="summary-value" style="font-size:16px">{_escape(habitat)}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Season</div>
                <div class="summary-value" style="font-size:16px">{_escape(str(season))}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">NDSI</div>
                <div class="summary-value">{file_indices.get('ndsi', 0):.3f}</div>
            </div>
        </div>
    </div>

    <!-- Charts -->
    <div class="panel">
        <h2>Soundscape Analysis</h2>
        <div class="charts-row">
            <div id="pie-chart" class="chart-box"></div>
            <div id="timeline-chart" class="chart-box"></div>
        </div>
        <div id="flux-chart" style="margin-top:15px; min-height:250px;"></div>
        <div id="indices-chart" style="margin-top:15px; min-height:300px;"></div>
    </div>

    <!-- Events -->
    <div class="panel">
        <h2>Detected Events ({n_events})</h2>
        {event_cards}
    </div>

    <footer>
        Parliament of the Living — Bioacoustic Event Detector v0.1.0<br>
        Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}
    </footer>
</div>

<script>
// Domain pie chart
var pieData = {pie_data};
Plotly.newPlot('pie-chart', [{{
    values: pieData.values,
    labels: pieData.labels,
    type: 'pie',
    marker: {{ colors: pieData.colors }},
    textinfo: 'label+percent',
    hole: 0.4
}}], {{
    title: 'Acoustic Domains',
    margin: {{ t: 40, b: 20, l: 20, r: 20 }},
    paper_bgcolor: 'transparent',
    font: {{ family: 'Segoe UI' }}
}}, {{ responsive: true }});

// Timeline
var tlData = {timeline_data};
if (tlData.length > 0) {{
    Plotly.newPlot('timeline-chart', tlData, {{
        title: 'Event Timeline',
        xaxis: {{ title: 'Time (s)' }},
        yaxis: {{ title: 'Event', showticklabels: false }},
        margin: {{ t: 40, b: 40, l: 40, r: 20 }},
        paper_bgcolor: 'transparent',
        barmode: 'stack',
        showlegend: true,
        font: {{ family: 'Segoe UI' }}
    }}, {{ responsive: true }});
}}

// Peak flux per event
var fluxData = {flux_data};
if (fluxData.x.length > 0) {{
    Plotly.newPlot('flux-chart', [{{
        x: fluxData.x, y: fluxData.y, type: 'bar',
        marker: {{ color: fluxData.colors }}, name: 'Peak flux',
        text: fluxData.roles, hovertemplate:
            '%{{text}}<br>onset %{{x:.1f}}s<br>peak flux %{{y:.2f}}<extra></extra>'
    }}], {{
        title: 'Peak Spectral Flux per Event',
        xaxis: {{ title: 'Onset time (s)' }},
        yaxis: {{ title: 'Peak flux' }},
        margin: {{ t: 40, b: 40, l: 50, r: 20 }},
        paper_bgcolor: 'transparent',
        font: {{ family: 'Segoe UI' }}
    }}, {{ responsive: true }});
}}

// Indices bar chart
var idxData = {indices_data};
if (idxData.labels.length > 0) {{
    var traces = Object.keys(idxData.indices).map(function(idx) {{
        return {{
            x: idxData.labels, y: idxData.indices[idx],
            name: idx.toUpperCase(), type: 'bar'
        }};
    }});
    Plotly.newPlot('indices-chart', traces, {{
        title: 'Acoustic Indices per Event',
        barmode: 'group',
        xaxis: {{ title: 'Event' }},
        margin: {{ t: 40, b: 40, l: 50, r: 20 }},
        paper_bgcolor: 'transparent',
        font: {{ family: 'Segoe UI' }}
    }}, {{ responsive: true }});
}}
</script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    return output_path


def generate_summary_report(all_results: list[dict], parliament: dict,
                            output_path: str, gallery_path: str = "",
                            phenology_path: str = "") -> str:
    """Generate a batch summary report across multiple recordings."""
    base = Path(output_path).parent
    n_files = len(all_results)
    total_events = sum(r.get("n_events", 0) for r in all_results)
    total_clips = sum(r.get("n_clips", 0) for r in all_results)
    n_roles = len(parliament.get("role_counts", {}))

    file_rows = "\n".join(
        f"""<tr>
            <td class="filename">{_escape(r.get('filename', ''))}</td>
            <td>{r.get('n_events', 0)}</td>
            <td>{r.get('n_clips', 0)}</td>
            <td>{_escape(_top_role(r))}</td>
            <td>{_escape(r.get('habitat', ''))}</td>
            <td>{r.get('ndsi', 0):.3f}</td>
            <td><a href="{_href(r.get('report_path', ''), base)}"
                   style="color:#667eea">View</a></td>
        </tr>"""
        for r in all_results
    )

    links = []
    if gallery_path:
        links.append(f'<a class="cta" href="{_href(gallery_path, base)}">'
                     f'Event clip gallery</a>')
    if phenology_path:
        links.append(f'<a class="cta" href="{_href(phenology_path, base)}">'
                     f'Phenological calendar</a>')
    links_html = f'<div class="links">{"".join(links)}</div>' if links else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Parliament of the Living - Batch Summary</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh; padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{
            color: white; text-align: center; margin-bottom: 25px;
            font-size: 2.2em; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        .panel {{
            background: white; padding: 20px; border-radius: 12px;
            margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .panel h2 {{ color: #2c3e50; margin-bottom: 15px; }}
        .summary-grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px; margin-bottom: 20px;
        }}
        .summary-item {{ text-align: center; }}
        .summary-label {{
            font-weight: 600; color: #7f8c8d; font-size: 11px;
            text-transform: uppercase; letter-spacing: 1px;
        }}
        .summary-value {{ color: #2c3e50; font-size: 28px; font-weight: bold; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; padding: 12px; text-align: left;
        }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #f0f0f0; }}
        tr:hover {{ background-color: #f8f9fa; }}
        .filename {{ font-family: monospace; font-size: 13px; }}
        .links {{ display: flex; gap: 12px; flex-wrap: wrap; }}
        .cta {{
            display: inline-block; padding: 10px 18px; border-radius: 8px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; text-decoration: none; font-weight: 600;
        }}
        footer {{
            margin-top: 30px; text-align: center; color: white; font-size: 13px;
        }}
    </style>
</head>
<body>
<div class="container">
    <h1>Parliament of the Living — Batch Summary</h1>
    <div class="panel">
        <div class="summary-grid">
            <div class="summary-item">
                <div class="summary-label">Recordings</div>
                <div class="summary-value">{n_files}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Total Events</div>
                <div class="summary-value">{total_events}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Event Clips</div>
                <div class="summary-value">{total_clips}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Democracy Index</div>
                <div class="summary-value">{parliament.get('democracy_index', 0):.2f}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Event Types</div>
                <div class="summary-value">{n_roles}</div>
            </div>
        </div>
        {links_html}
    </div>
    <div class="panel">
        <h2>Recordings</h2>
        <table>
            <tr><th>File</th><th>Events</th><th>Clips</th><th>Dominant role</th>
                <th>Habitat</th><th>NDSI</th><th>Report</th></tr>
            {file_rows}
        </table>
    </div>
    <footer>Bioacoustic toolkit — {datetime.now().strftime('%Y-%m-%d %H:%M')}</footer>
</div>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    return output_path


# --- Helper functions ---

def _escape(text: str) -> str:
    """HTML-escape text."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _top_role(result: dict) -> str:
    """Most frequent ecological role in a recording."""
    roles = result.get("parliament", {}).get("role_counts", {})
    if not roles:
        return "—"
    return max(roles, key=roles.get).replace("_", " ")


def _event_card_html(event: dict, index: int, base: Path) -> str:
    """Build HTML for a single event card."""
    domain = event.get("domain", "")
    role = event.get("role", "unknown").replace("_", " ").title()
    onset = event.get("onset_s", 0)
    offset = event.get("offset_s", 0)
    duration = offset - onset
    confidence = event.get("confidence", 0)
    centroid = event.get("centroid", 0)
    band = event.get("dominant_band", "").replace("_", " ")

    video_path = event.get("video_path", "")
    poster_path = event.get("poster_path", "")

    media_html = ""
    if video_path and Path(video_path).exists():
        poster_attr = ""
        if poster_path and Path(poster_path).exists():
            poster_attr = f' poster="{_href(poster_path, base)}"'
        media_html = (f'<video controls preload="metadata"{poster_attr}>'
                      f'<source src="{_href(video_path, base)}" type="video/mp4">'
                      f'</video>')
    elif poster_path and Path(poster_path).exists():
        media_html = (f'<img src="{_href(poster_path, base)}" '
                      f'alt="{role} spectrogram" style="width:100%;max-width:800px;'
                      f'border-radius:8px;margin-top:8px">')

    links = [
        f'<a href="{_href(event[key], base)}"{extra}>{label}</a>'
        for key, label, extra in (
            ("clip_path", "wav", " download"),
            ("gif_path", "gif", ' target="_blank"'),
            ("poster_path", "png", ' target="_blank"'),
        )
        if event.get(key) and Path(event[key]).exists()
    ]
    links_html = (f'<div class="event-links">{" ".join(links)}</div>'
                  if links else "")

    reasoning = _escape(event.get("reasoning", ""))

    return f"""<div class="event-card {domain}">
        <div class="event-header">
            <div class="event-title">Event {index}: {role}</div>
            <span class="event-badge badge-{domain}">{domain}</span>
        </div>
        <div class="event-meta">
            <div>Time: <span>{onset:.1f}s — {offset:.1f}s</span></div>
            <div>Duration: <span>{duration:.1f}s</span></div>
            <div>Confidence: <span>{confidence:.0%}</span></div>
            <div>Centroid: <span>{centroid:.0f} Hz</span></div>
            <div>Band: <span>{band}</span></div>
            <div>ACI: <span>{event.get('aci', 0):.2f}</span></div>
            <div>NDSI: <span>{event.get('ndsi', 0):.3f}</span></div>
        </div>
        <div class="event-why">{reasoning}</div>
        {media_html}
        {links_html}
    </div>"""


def _build_pie_data(parliament: dict) -> dict:
    """Build Plotly pie chart data from parliament summary."""
    domain_pcts = parliament.get("domain_percentages", {})
    color_map = {
        "biophony": "#27ae60", "geophony": "#3498db",
        "anthrophony": "#e74c3c", "transition": "#f39c12",
    }
    labels = list(domain_pcts.keys())
    values = list(domain_pcts.values())
    colors = [color_map.get(d, "#95a5a6") for d in labels]
    return {"labels": labels, "values": values, "colors": colors}


def _build_timeline_data(events: list[dict]) -> list[dict]:
    """Build Plotly horizontal bar data for event timeline."""
    color_map = {
        "biophony": "#27ae60", "geophony": "#3498db",
        "anthrophony": "#e74c3c", "transition": "#f39c12",
    }
    traces = {}
    for e in events:
        domain = e.get("domain", "unknown")
        if domain not in traces:
            traces[domain] = {"x": [], "y": [], "base": [],
                              "name": domain, "type": "bar",
                              "orientation": "h",
                              "marker": {"color": color_map.get(domain, "#95a5a6")}}
        dur = e.get("offset_s", 0) - e.get("onset_s", 0)
        traces[domain]["x"].append(dur)
        traces[domain]["y"].append(1)
        traces[domain]["base"].append(e.get("onset_s", 0))

    return list(traces.values())


def _build_flux_data(events: list[dict]) -> dict:
    """
    Peak spectral flux per event, coloured by acoustic domain.

    The full frame-by-frame flux curve is not kept in events.json (it is far
    larger than everything else combined), so this charts the per-event peaks
    that triggered detection.
    """
    color_map = {
        "biophony": "#27ae60", "geophony": "#3498db",
        "anthrophony": "#e74c3c", "transition": "#f39c12",
    }
    return {
        "x": [e.get("onset_s", 0) for e in events],
        "y": [e.get("peak_flux", 0) for e in events],
        "colors": [color_map.get(e.get("domain", ""), "#95a5a6") for e in events],
        "roles": [e.get("role", "") for e in events],
    }


def _build_indices_data(events: list[dict]) -> dict:
    """Build per-event acoustic indices for bar chart."""
    labels = [f"E{i+1}" for i in range(len(events))]
    index_names = ["aci", "ndsi", "adi"]
    indices = {}
    for name in index_names:
        indices[name] = [e.get(name, 0) for e in events]
    return {"labels": labels, "indices": indices}
