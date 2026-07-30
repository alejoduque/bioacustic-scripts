"""
Event-clip gallery.

Single replacement for the two byte-identical shell generators
(enhanced_html_generator.sh and make-html-lightbox-table-fixed.sh), which built
one gallery row per *recording*. This builds one card per *event*, grouped by
ecological role, with a self-contained lightbox video player — no perfundo, no
external CSS, no CDN.
"""

import html
import json
from datetime import datetime
from pathlib import Path

DOMAIN_COLORS = {
    "biophony": "#27ae60",
    "geophony": "#3498db",
    "anthrophony": "#e74c3c",
    "transition": "#f39c12",
}


def _rel(path: str, base: Path) -> str:
    """Path relative to the gallery file, URL-encoded enough for hrefs."""
    if not path:
        return ""
    try:
        rel = Path(path).resolve().relative_to(base.resolve())
    except ValueError:
        rel = Path(path)
    return str(rel).replace(" ", "%20").replace("#", "%23")


def collect_gallery_items(results: list[dict], base_dir: str) -> list[dict]:
    """
    Flatten per-recording results into one record per event clip.

    Only events that actually produced a clip are included; an event with no
    media has nothing to show in a gallery.
    """
    base = Path(base_dir)
    items = []

    for result in results:
        rec_dt = result.get("datetime")
        date_str = rec_dt.strftime("%Y-%m-%d %H:%M") if rec_dt else ""
        for event in result.get("events", []):
            if not (event.get("clip_path") or event.get("video_path")):
                continue
            items.append({
                "role": event.get("role", "unclassified"),
                "domain": event.get("domain", "unknown"),
                "confidence": event.get("confidence", 0.0),
                "onset_s": event.get("onset_s", 0.0),
                "duration_s": event.get("duration_s", 0.0),
                "band": event.get("dominant_band", ""),
                "centroid": event.get("centroid", 0.0),
                "ndsi": event.get("ndsi", 0.0),
                "aci": event.get("aci", 0.0),
                "reasoning": event.get("reasoning", ""),
                "source": result.get("filename", ""),
                "habitat": result.get("habitat", ""),
                "season": result.get("season", "") or "",
                "date": date_str,
                "video": _rel(event.get("video_path", ""), base),
                "poster": _rel(event.get("thumbnail_path", "")
                               or event.get("poster_path", ""), base),
                "audio": _rel(event.get("clip_path", ""), base),
                "gif": _rel(event.get("gif_path", ""), base),
            })

    items.sort(key=lambda i: (i["domain"], i["role"], -i["confidence"]))
    return items


def _sites_html(results: list[dict], base: Path) -> str:
    """
    One row per source recording, with GPS entry.

    Carried over from the shell generator this replaces: coordinates are stored
    in localStorage under the same 'audiomoth-gps' key and keyed by recording
    stem, so tags saved by the old gallery still show up here. GPS belongs to
    the deployment, not to individual events, hence a per-recording table.
    """
    rows = []
    for result in results:
        filename = result.get("filename", "")
        stem = Path(filename).stem
        rec_dt = result.get("datetime")
        rows.append(f"""<tr data-file="{html.escape(stem)}">
  <td class="mono">{html.escape(filename)}</td>
  <td>{html.escape(str(result.get('habitat', '') or '—'))}</td>
  <td>{html.escape(rec_dt.strftime('%Y-%m-%d %H:%M') if rec_dt else '—')}</td>
  <td>{result.get('n_events', 0)}</td>
  <td>{result.get('n_clips', 0)}</td>
  <td class="gps">
    <input class="gps-lat" data-file="{html.escape(stem)}" placeholder="lat"
           inputmode="decimal">
    <input class="gps-lng" data-file="{html.escape(stem)}" placeholder="lng"
           inputmode="decimal">
    <button class="mini save" data-file="{html.escape(stem)}">save</button>
    <button class="mini map" data-file="{html.escape(stem)}">map</button>
    <button class="mini clear" data-file="{html.escape(stem)}">clear</button>
    <span class="gps-out" id="gps-{html.escape(stem)}"></span>
  </td>
  <td>{f'<a href="{_rel(result.get("report_path", ""), base)}">report</a>'
      if result.get('report_path') else '—'}</td>
</tr>""")

    return f"""<section class="group">
  <header class="group-head" style="--accent:#667eea">
    <h2>Recording sites</h2>
    <span class="count">{len(results)} recording{'s' if len(results) != 1 else ''}</span>
    <span class="count" id="gps-count"></span>
  </header>
  <div class="table-wrap">
    <table>
      <tr><th>File</th><th>Habitat</th><th>When</th><th>Events</th>
          <th>Clips</th><th>Coordinates</th><th></th></tr>
      {''.join(rows)}
    </table>
  </div>
</section>"""


def generate_gallery(results: list[dict], output_path: str,
                     reels: dict[str, str] | None = None,
                     phenology_link: str = "",
                     title: str = "Parliament of the Living") -> str:
    """Write the event-clip gallery HTML. Returns the path written."""
    out = Path(output_path)
    base = out.parent
    items = collect_gallery_items(results, str(base))

    reel_links = {role: _rel(path, base)
                  for role, path in (reels or {}).items()}

    role_counts: dict[str, int] = {}
    domain_counts: dict[str, int] = {}
    for item in items:
        role_counts[item["role"]] = role_counts.get(item["role"], 0) + 1
        domain_counts[item["domain"]] = domain_counts.get(item["domain"], 0) + 1

    groups = "\n".join(
        _group_html(role, [i for i in items if i["role"] == role],
                    reel_links.get(role, ""))
        for role in sorted(role_counts, key=lambda r: -role_counts[r])
    )

    filter_chips = "\n".join(
        f'<button class="chip" data-domain="{html.escape(d)}" '
        f'style="--chip:{DOMAIN_COLORS.get(d, "#95a5a6")}">'
        f'{html.escape(d)} <b>{n}</b></button>'
        for d, n in sorted(domain_counts.items(), key=lambda kv: -kv[1])
    )

    pheno_html = ""
    if phenology_link:
        pheno_html = (
            f'<a class="pill" href="{_rel(phenology_link, base)}">'
            f'Phenological calendar &rarr;</a>'
        )

    html_doc = _TEMPLATE.format(
        title=html.escape(title),
        n_clips=len(items),
        n_roles=len(role_counts),
        n_recordings=len(results),
        filter_chips=filter_chips,
        groups=groups or '<p class="empty">No event clips were produced.</p>',
        sites=_sites_html(results, base),
        pheno_html=pheno_html,
        domain_colors=json.dumps(DOMAIN_COLORS),
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    out.write_text(html_doc, encoding="utf-8")
    return str(out)


def _group_html(role: str, items: list[dict], reel_link: str) -> str:
    """One collapsible section per ecological role."""
    label = html.escape(role.replace("_", " ").title())
    domain = items[0]["domain"] if items else "unknown"
    color = DOMAIN_COLORS.get(domain, "#95a5a6")

    reel = ""
    if reel_link:
        reel = (f'<a class="pill" href="#" data-video="{reel_link}" '
                f'data-title="{label} — full reel">Play reel ({len(items)})</a>')

    cards = "\n".join(_card_html(i) for i in items)

    return f"""<section class="group" data-domain="{html.escape(domain)}">
  <header class="group-head" style="--accent:{color}">
    <h2>{label}</h2>
    <span class="count">{len(items)} clip{'s' if len(items) != 1 else ''}</span>
    <span class="badge" style="background:{color}">{html.escape(domain)}</span>
    {reel}
  </header>
  <div class="grid">
    {cards}
  </div>
</section>"""


def _card_html(item: dict) -> str:
    color = DOMAIN_COLORS.get(item["domain"], "#95a5a6")
    title = html.escape(item["role"].replace("_", " ").title())
    meta_line = f'{item["onset_s"]:.0f}s · {item["duration_s"]:.1f}s · {item["confidence"]:.0%}'

    if item["poster"]:
        cover = f'<img loading="lazy" src="{item["poster"]}" alt="{title} spectrogram">'
    else:
        cover = f'<div class="no-cover" style="background:{color}22">no spectrogram</div>'

    play_attrs = ""
    if item["video"]:
        play_attrs = (f' data-video="{item["video"]}"'
                      f' data-title="{title} — {html.escape(item["source"])}"')

    links = []
    if item["audio"]:
        links.append(f'<a href="{item["audio"]}" download>wav</a>')
    if item["gif"]:
        links.append(f'<a href="{item["gif"]}" target="_blank">gif</a>')
    if item["video"]:
        links.append(f'<a href="{item["video"]}" target="_blank">mp4</a>')

    search_blob = html.escape(" ".join([
        item["role"], item["domain"], item["source"], item["habitat"],
        item["season"], item["band"], item["date"],
    ]).lower())

    return f"""<article class="card" data-domain="{html.escape(item['domain'])}"
      data-search="{search_blob}" style="--accent:{color}">
  <div class="cover"{play_attrs}>{cover}
    {'<span class="play">▶</span>' if item['video'] else ''}
  </div>
  <div class="body">
    <div class="title">{title}</div>
    <div class="sub">{html.escape(item['source'])}</div>
    <div class="meta">{meta_line}</div>
    <dl>
      <div><dt>band</dt><dd>{html.escape(item['band'].replace('_', ' '))}</dd></div>
      <div><dt>centroid</dt><dd>{item['centroid']:.0f} Hz</dd></div>
      <div><dt>NDSI</dt><dd>{item['ndsi']:+.2f}</dd></div>
      <div><dt>ACI</dt><dd>{item['aci']:.1f}</dd></div>
    </dl>
    <p class="why">{html.escape(item['reasoning'])}</p>
    <div class="links">{' '.join(links)}</div>
  </div>
</article>"""


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Event Clips</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh; padding: 20px; color: #2c3e50;
  }}
  .container {{ max-width: 1500px; margin: 0 auto; }}
  h1 {{ color: #fff; text-align: center; font-size: 2.2em;
       text-shadow: 2px 2px 4px rgba(0,0,0,.3); }}
  .subtitle {{ color: rgba(255,255,255,.85); text-align: center;
              margin: 6px 0 22px; }}
  .toolbar {{
    background: #fff; border-radius: 12px; padding: 14px 16px;
    margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,.1);
    display: flex; gap: 10px; flex-wrap: wrap; align-items: center;
  }}
  .chip, .pill {{
    border: 2px solid var(--chip, #667eea); background: transparent;
    color: #2c3e50; padding: 5px 12px; border-radius: 999px;
    font-size: 13px; cursor: pointer; text-decoration: none;
  }}
  .chip.off {{ opacity: .35; }}
  .chip b {{ color: var(--chip, #667eea); }}
  .pill {{ --chip: #667eea; font-weight: 600; }}
  input[type=search] {{
    flex: 1 1 220px; min-width: 180px; padding: 8px 12px;
    border: 1px solid #dfe4ea; border-radius: 8px; font-size: 14px;
  }}
  .group {{
    background: #fff; border-radius: 12px; padding: 18px;
    margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,.1);
  }}
  .group-head {{
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    border-bottom: 2px solid var(--accent); padding-bottom: 10px;
    margin-bottom: 14px;
  }}
  .group-head h2 {{ font-size: 1.3em; }}
  .count {{ color: #7f8c8d; font-size: 13px; }}
  .badge {{ color: #fff; font-size: 11px; font-weight: 600;
           padding: 3px 10px; border-radius: 12px; }}
  .grid {{
    display: grid; gap: 16px;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  }}
  .card {{
    border: 1px solid #eef0f4; border-left: 4px solid var(--accent);
    border-radius: 10px; overflow: hidden; background: #fcfcfd;
    display: flex; flex-direction: column;
  }}
  .cover {{ position: relative; cursor: pointer; background: #11121a; }}
  .cover img {{ display: block; width: 100%; height: auto; }}
  .no-cover {{ padding: 38px 10px; text-align: center; color: #7f8c8d;
              font-size: 12px; }}
  .play {{
    position: absolute; inset: 0; display: grid; place-items: center;
    color: #fff; font-size: 34px; text-shadow: 0 2px 8px rgba(0,0,0,.6);
    opacity: .85;
  }}
  .body {{ padding: 12px 14px 14px; }}
  .title {{ font-weight: 600; }}
  .sub {{ font-family: ui-monospace, monospace; font-size: 12px;
         color: #7f8c8d; word-break: break-all; }}
  .meta {{ font-size: 12px; color: #55606b; margin: 6px 0 8px; }}
  dl {{ display: grid; grid-template-columns: 1fr 1fr; gap: 4px 10px;
       font-size: 12px; margin-bottom: 8px; }}
  dt {{ color: #95a5a6; display: inline; }}
  dd {{ display: inline; font-weight: 600; }}
  .why {{ font-size: 12px; color: #7f8c8d; font-style: italic; }}
  .links {{ margin-top: 10px; display: flex; gap: 10px; font-size: 12px; }}
  .links a {{ color: #667eea; text-decoration: none; }}
  .empty {{ color: #7f8c8d; }}
  /* recording sites table */
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: #fff; padding: 10px; text-align: left; white-space: nowrap;
  }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #f0f0f0;
       vertical-align: middle; }}
  td.mono {{ font-family: ui-monospace, monospace; }}
  td a {{ color: #667eea; text-decoration: none; }}
  .gps {{ white-space: nowrap; }}
  .gps input {{
    width: 84px; padding: 4px 6px; border: 1px solid #dfe4ea;
    border-radius: 5px; font-size: 12px;
  }}
  .mini {{
    border: none; border-radius: 5px; padding: 4px 8px; font-size: 11px;
    cursor: pointer; color: #fff; margin-left: 2px;
  }}
  .mini.save {{ background: #27ae60; }}
  .mini.map {{ background: #3498db; }}
  .mini.clear {{ background: #e74c3c; }}
  .gps-out {{ margin-left: 8px; font-size: 11px; color: #7f8c8d; }}
  footer {{ text-align: center; color: #fff; font-size: 13px; margin: 28px 0 8px; }}
  /* lightbox */
  #lb {{
    position: fixed; inset: 0; background: rgba(10,10,15,.92);
    display: none; place-items: center; z-index: 50; padding: 24px;
  }}
  #lb.on {{ display: grid; }}
  #lb video {{ max-width: min(1100px, 94vw); max-height: 80vh;
              border-radius: 10px; background: #000; }}
  #lb .cap {{ color: #fff; text-align: center; margin-top: 12px; }}
  #lb .x {{ position: absolute; top: 18px; right: 24px; color: #fff;
           font-size: 30px; cursor: pointer; }}
  @media (max-width: 600px) {{ dl {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="container">
  <h1>{title}</h1>
  <div class="subtitle">
    {n_clips} event clips · {n_roles} event types · {n_recordings} recordings
  </div>

  <div class="toolbar">
    <input type="search" id="q" placeholder="Filter by role, file, habitat, band…">
    {filter_chips}
    {pheno_html}
  </div>

  {groups}

  {sites}

  <footer>Bioacoustic toolkit — event gallery · generated {generated}</footer>
</div>

<div id="lb"><span class="x">&times;</span>
  <div><video id="lbv" controls preload="metadata"></video>
  <div class="cap" id="lbc"></div></div>
</div>

<script>
const DOMAIN_COLORS = {domain_colors};
const lb = document.getElementById('lb');
const lbv = document.getElementById('lbv');
const lbc = document.getElementById('lbc');

function openLightbox(src, title) {{
  lbv.src = src; lbc.textContent = title || '';
  lb.classList.add('on'); lbv.play().catch(() => {{}});
}}
function closeLightbox() {{
  lb.classList.remove('on'); lbv.pause(); lbv.removeAttribute('src'); lbv.load();
}}

document.addEventListener('click', (e) => {{
  const trigger = e.target.closest('[data-video]');
  if (trigger) {{
    e.preventDefault();
    openLightbox(trigger.dataset.video, trigger.dataset.title);
    return;
  }}
  if (e.target === lb || e.target.classList.contains('x')) closeLightbox();
}});
document.addEventListener('keydown', (e) => {{
  if (e.key === 'Escape') closeLightbox();
}});

// Domain chips + text search
const hidden = new Set();
function applyFilters() {{
  const q = (document.getElementById('q').value || '').trim().toLowerCase();
  document.querySelectorAll('.card').forEach(card => {{
    const domainOk = !hidden.has(card.dataset.domain);
    const textOk = !q || (card.dataset.search || '').includes(q);
    card.style.display = (domainOk && textOk) ? '' : 'none';
  }});
  document.querySelectorAll('.group').forEach(group => {{
    const any = [...group.querySelectorAll('.card')]
      .some(c => c.style.display !== 'none');
    group.style.display = any ? '' : 'none';
  }});
}}
document.querySelectorAll('.chip').forEach(chip => {{
  chip.addEventListener('click', () => {{
    const d = chip.dataset.domain;
    if (hidden.has(d)) {{ hidden.delete(d); chip.classList.remove('off'); }}
    else {{ hidden.add(d); chip.classList.add('off'); }}
    applyFilters();
  }});
}});
document.getElementById('q').addEventListener('input', applyFilters);

// Per-recording GPS tagging. Same localStorage key and per-recording keying as
// the shell gallery this replaces, so coordinates saved there still load here.
const GPS_KEY = 'audiomoth-gps';
let gps = {{}};
try {{ gps = JSON.parse(localStorage.getItem(GPS_KEY) || '{{}}'); }} catch (e) {{}}

function validCoords(lat, lng) {{
  const a = parseFloat(lat), b = parseFloat(lng);
  return !isNaN(a) && !isNaN(b) && a >= -90 && a <= 90 && b >= -180 && b <= 180;
}}
function showGps(file) {{
  const out = document.getElementById('gps-' + file);
  if (!out) return;
  const d = gps[file];
  out.textContent = d ? `${{d.lat}}, ${{d.lng}}` : '';
}}
function countGps() {{
  const el = document.getElementById('gps-count');
  if (!el) return;
  const n = Object.keys(gps).length;
  el.textContent = n ? `${{n}} with coordinates` : '';
}}
function persist() {{
  try {{ localStorage.setItem(GPS_KEY, JSON.stringify(gps)); }}
  catch (e) {{ console.warn('Could not save coordinates', e); }}
  countGps();
}}
function inputsFor(file) {{
  return [
    document.querySelector(`.gps-lat[data-file="${{file}}"]`),
    document.querySelector(`.gps-lng[data-file="${{file}}"]`),
  ];
}}

document.querySelectorAll('.mini').forEach(button => {{
  button.addEventListener('click', () => {{
    const file = button.dataset.file;
    const [lat, lng] = inputsFor(file);
    if (button.classList.contains('save')) {{
      if (!validCoords(lat.value, lng.value)) {{
        alert('Enter valid coordinates (lat -90..90, lng -180..180).');
        return;
      }}
      gps[file] = {{ lat: lat.value.trim(), lng: lng.value.trim() }};
      persist(); showGps(file);
      const label = button.textContent;
      button.textContent = 'saved';
      setTimeout(() => {{ button.textContent = label; }}, 900);
    }} else if (button.classList.contains('map')) {{
      const d = gps[file];
      if (!d) {{ alert('No coordinates saved for this recording yet.'); return; }}
      window.open(`https://www.google.com/maps?q=${{d.lat}},${{d.lng}}`, '_blank');
    }} else {{
      delete gps[file];
      lat.value = ''; lng.value = '';
      persist(); showGps(file);
    }}
  }});
}});

Object.keys(gps).forEach(file => {{
  const [lat, lng] = inputsFor(file);
  if (lat && lng) {{ lat.value = gps[file].lat; lng.value = gps[file].lng; }}
  showGps(file);
}});
countGps();
</script>
</body>
</html>"""
