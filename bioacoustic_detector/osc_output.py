"""
OSC (Open Sound Control) output.

Two payloads:

  events     — one burst of messages per detected acoustic event
  phenology  — the daily calendar replayed as a time-compressed season

Three delivery modes for each:

  file    text bundle (timestamp / address / args), diffable and archivable
  score   SuperCollider .scd, playable with Score.play or NRT-renderable
  live    UDP to a host:port, in real time or compressed time

Phenology is the point of the toolkit: a season of AudioMoth recordings
becomes a stream an instrument can follow. Every scalar arrives twice — raw
value first, then the same value scaled to 0..1 — so a patch can take whichever
it needs without knowing the dataset's range.

Address map: see write_osc_manifest() or docs printed by
`./bioacoustics.sh` -> OSC -> "show address map".
"""

import math
import sys
import time
from pathlib import Path

from .config import OSCConfig
from .phenology import CV_FIELDS

# Eurorack mapping constants
VOCT_REF_HZ = 261.63  # Middle C
VOCT_REF_V = 0.0

# ILDA color mapping for frequency bands
ILDA_BAND_COLORS = {
    "geophony": 1,       # Red
    "biophony_low": 2,   # Green
    "biophony_mid": 3,   # Blue
    "biophony_high": 4,  # Yellow
    "ultrasonic": 5,     # Cyan
}


def hz_to_voct(hz: float) -> float:
    """Convert frequency in Hz to V/Oct voltage (log-scaled)."""
    if hz <= 0:
        return -5.0
    return VOCT_REF_V + math.log2(hz / VOCT_REF_HZ)


# --- event messages ---------------------------------------------------------

def build_event_osc_messages(event: dict, recording_meta: dict,
                             namespace: str = "/parliament") -> list[tuple[str, list]]:
    """
    Build OSC messages for a single event.

    Returns list of (address, [args]) tuples.
    """
    onset = event.get("onset_s", 0)
    duration = event.get("offset_s", 0) - onset
    role = event.get("role", "unknown")
    domain = event.get("domain", "unknown")
    band = event.get("dominant_band", "unknown")
    centroid = event.get("centroid", 440.0)
    flatness = event.get("flatness", 0.0)
    flux = event.get("peak_flux", 0.0)
    confidence = event.get("confidence", 0.0)

    aci = event.get("aci", 0.0)
    ndsi = event.get("ndsi", 0.0)
    bio = event.get("bio", 0.0)
    adi = event.get("adi", 0.0)

    habitat = recording_meta.get("habitat", "unknown")
    season = recording_meta.get("season", "unknown")
    temp = recording_meta.get("temperature_c", 0.0) or 0.0
    dt = recording_meta.get("datetime")
    hour = dt.hour if dt else 0
    democracy = recording_meta.get("democracy_index", 0.0)

    ns = namespace.rstrip("/")
    return [
        (f"{ns}/event", [1]),  # bang
        (f"{ns}/event/onset", [float(onset)]),
        (f"{ns}/event/duration", [float(duration)]),
        (f"{ns}/event/role", [str(role)]),
        (f"{ns}/event/domain", [str(domain)]),
        (f"{ns}/event/band", [str(band)]),
        (f"{ns}/event/centroid", [float(centroid)]),
        (f"{ns}/event/voct", [float(hz_to_voct(centroid))]),
        (f"{ns}/event/flatness", [float(flatness)]),
        (f"{ns}/event/flux", [float(flux)]),
        (f"{ns}/event/confidence", [float(confidence)]),
        (f"{ns}/event/aci", [float(aci)]),
        (f"{ns}/event/ndsi", [float(ndsi)]),
        (f"{ns}/event/bio", [float(bio)]),
        (f"{ns}/event/adi", [float(adi)]),
        (f"{ns}/habitat", [str(habitat)]),
        (f"{ns}/season", [str(season or "unknown")]),
        (f"{ns}/temperature", [float(temp)]),
        (f"{ns}/hour", [int(hour)]),
        (f"{ns}/democracy_index", [float(democracy)]),
        # ILDA mappings
        ("/ilda/color", [ILDA_BAND_COLORS.get(band, 0)]),
        ("/ilda/intensity", [float(confidence)]),
        ("/ilda/angle", [float(min(centroid / 10000.0, 1.0))]),
        ("/ilda/speed", [float(min(flux / 100.0, 1.0))]),
    ]


# --- phenology messages -----------------------------------------------------

def build_phenology_frame_messages(frame: dict, day_index: int = 0,
                                   namespace: str = "/phenology"
                                   ) -> list[tuple[str, list]]:
    """
    Build the OSC burst for one day of the phenological calendar.

    Each scalar goes out as [raw, cv] so patches can use absolute values
    (ecology) or normalized ones (control voltage) interchangeably.
    """
    ns = namespace.rstrip("/")
    cv = frame.get("cv", {})

    messages: list[tuple[str, list]] = [
        (f"{ns}/day", [int(day_index),
                       str(frame.get("date", "")),
                       int(frame.get("day_of_year", 0))]),
        (f"{ns}/day/recordings", [int(frame.get("n_recordings", 0))]),
        (f"{ns}/day/events", [int(frame.get("n_events", 0))]),
    ]

    for field in CV_FIELDS:
        raw = frame.get(field)
        messages.append((f"{ns}/day/{field}",
                         [float(raw) if raw is not None else 0.0,
                          float(cv.get(field, 0.0))]))

    messages.append((f"{ns}/day/dominant_role",
                     [str(frame.get("dominant_role", "silence"))]))

    total = max(int(frame.get("n_events", 0)), 1)
    for role, count in sorted(frame.get("role_counts", {}).items(),
                              key=lambda kv: -kv[1]):
        messages.append((f"{ns}/day/role",
                         [str(role), int(count), round(count / total, 4)]))

    hourly = frame.get("hourly_events", {})
    messages.append((f"{ns}/day/hourly",
                     [int(hourly.get(h, hourly.get(str(h), 0))) for h in range(24)]))

    return messages


def build_phenology_event_messages(pheno_event: dict,
                                   namespace: str = "/phenology"
                                   ) -> list[tuple[str, list]]:
    """Build OSC messages for a detected phenological shift."""
    ns = namespace.rstrip("/")
    return [
        (f"{ns}/event", [str(pheno_event.get("type", "unknown")),
                         str(pheno_event.get("date", "")),
                         int(pheno_event.get("day_of_year", 0)),
                         float(pheno_event.get("magnitude", 0.0))]),
        (f"{ns}/event/type", [str(pheno_event.get("type", "unknown"))]),
        (f"{ns}/event/day_of_year", [int(pheno_event.get("day_of_year", 0))]),
    ]


def build_phenology_header_messages(calendar: dict, config: OSCConfig | None = None
                                    ) -> list[tuple[str, list]]:
    """
    Build the preamble a receiver needs before the day frames start:
    dataset extent, playback speed, normalization ranges, diel wavetable.
    """
    config = config or OSCConfig()
    ns = config.phenology_namespace.rstrip("/")
    frames = calendar.get("frames", [])

    messages: list[tuple[str, list]] = [
        (f"{ns}/meta", [int(len(frames)),
                        str(frames[0]["date"]) if frames else "",
                        str(frames[-1]["date"]) if frames else "",
                        float(config.days_per_second)]),
    ]

    for field, span in calendar.get("ranges", {}).items():
        messages.append((f"{ns}/range/{field}",
                         [float(span.get("min", 0.0)), float(span.get("max", 0.0))]))

    diel = calendar.get("diel_table", [])
    if diel:
        messages.append((f"{ns}/diel/table", [float(v) for v in diel]))
        peak_hour = max(range(len(diel)), key=lambda h: diel[h])
        messages.append((f"{ns}/diel/peak_hour", [int(peak_hour)]))

    dawn = calendar.get("dawn_chorus_times", [])
    if dawn:
        minutes = [d["onset_minutes"] for d in dawn]
        messages.append((f"{ns}/dawn_chorus/mean", [float(sum(minutes) / len(minutes))]))
        messages.append((f"{ns}/dawn_chorus/first", [float(min(minutes))]))
        messages.append((f"{ns}/dawn_chorus/last", [float(max(minutes))]))

    return messages


def phenology_timeline(calendar: dict, config: OSCConfig | None = None
                       ) -> list[tuple[float, str, list]]:
    """
    Flatten the calendar into a timed message list: (time_s, address, args).

    Day N is scheduled at N / days_per_second seconds, so a 90-day season at
    the default 1 day/s plays in a minute and a half. Phenological shifts ride
    along on the day they occur.
    """
    config = config or OSCConfig()
    ns = config.phenology_namespace.rstrip("/")
    frames = calendar.get("frames", [])
    rate = config.days_per_second if config.days_per_second > 0 else 1.0

    timeline: list[tuple[float, str, list]] = [
        (0.0, addr, args)
        for addr, args in build_phenology_header_messages(calendar, config)
    ]

    date_to_slot = {}
    for index, frame in enumerate(frames):
        at = index / rate
        date_to_slot[frame.get("date")] = at
        for addr, args in build_phenology_frame_messages(frame, index, ns):
            timeline.append((at, addr, args))

    for pheno_event in calendar.get("phenological_events", []):
        at = date_to_slot.get(pheno_event.get("date"), 0.0)
        for addr, args in build_phenology_event_messages(pheno_event, ns):
            timeline.append((at + 1e-3, addr, args))  # just after the day frame

    if frames:
        timeline.append((len(frames) / rate, f"{ns}/end", [1]))

    timeline.sort(key=lambda item: item[0])
    return timeline


def event_timeline(events: list[dict], recording_meta: dict,
                   config: OSCConfig | None = None
                   ) -> list[tuple[float, str, list]]:
    """Flatten events into a timed message list at their onset times."""
    config = config or OSCConfig()
    ns = config.namespace
    timeline = []
    for event in sorted(events, key=lambda e: e.get("onset_s", 0)):
        onset = float(event.get("onset_s", 0))
        for addr, args in build_event_osc_messages(event, recording_meta, ns):
            timeline.append((onset, addr, args))
    return timeline


# --- file writers -----------------------------------------------------------

def _write_timeline(timeline: list[tuple[float, str, list]], output_path: str) -> str:
    """Write a timed message list as a tab-separated bundle file."""
    lines = [
        f"{at:.4f}\t{addr}\t" + "\t".join(str(a) for a in args)
        for at, addr, args in timeline
    ]
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def write_osc_bundle_file(events: list[dict], recording_meta: dict,
                          output_path: str,
                          phenology_events: list[dict] | None = None,
                          config: OSCConfig | None = None) -> str:
    """
    Write event OSC messages to a text bundle file.

    Format: one line per message, tab-separated:
    timestamp_s<TAB>address<TAB>arg1<TAB>arg2<TAB>...
    """
    config = config or OSCConfig()
    timeline = event_timeline(events, recording_meta, config)

    if phenology_events:
        ns = config.phenology_namespace
        for pheno_event in phenology_events:
            for addr, args in build_phenology_event_messages(pheno_event, ns):
                timeline.append((0.0, addr, args))
        timeline.sort(key=lambda item: item[0])

    return _write_timeline(timeline, output_path)


def write_phenology_osc_file(calendar: dict, output_path: str,
                             config: OSCConfig | None = None) -> str:
    """Write the phenological calendar as a timed OSC bundle file."""
    return _write_timeline(phenology_timeline(calendar, config), output_path)


def generate_supercollider_score(events: list[dict], recording_meta: dict,
                                 output_path: str,
                                 phenology_events: list[dict] | None = None,
                                 config: OSCConfig | None = None) -> str:
    """
    Generate a SuperCollider Score (.scd) file for detected events.

    Format compatible with Score.newFromFile and NRT rendering.
    """
    config = config or OSCConfig()
    timeline = event_timeline(events, recording_meta, config)

    if phenology_events:
        for pheno_event in phenology_events:
            for addr, args in build_phenology_event_messages(
                    pheno_event, config.phenology_namespace):
                timeline.append((0.0, addr, args))
        timeline.sort(key=lambda item: item[0])

    header = [
        "// SuperCollider Score — Parliament of the Living (events)",
        f"// Source: {recording_meta.get('filename', 'unknown')}",
        f"// Habitat: {recording_meta.get('habitat', 'unknown')}",
        "",
        "// Eurorack mapping notes:",
        "//   centroid -> V/Oct pitch CV (also sent pre-converted on /event/voct)",
        "//   flux -> gate/trigger intensity",
        "//   flatness -> timbre CV (0=tonal, 1=noise)",
        "//   NDSI -> bipolar CV (-5V to +5V: -1=anthrophony, +1=biophony)",
    ]
    return _write_sc_score(timeline, output_path, header)


def generate_phenology_supercollider_score(calendar: dict, output_path: str,
                                           config: OSCConfig | None = None) -> str:
    """Generate a SuperCollider Score (.scd) for the phenological calendar."""
    config = config or OSCConfig()
    frames = calendar.get("frames", [])
    header = [
        "// SuperCollider Score — Phenological calendar",
        f"// Days: {len(frames)}"
        + (f" ({frames[0]['date']} .. {frames[-1]['date']})" if frames else ""),
        f"// Playback: {config.days_per_second} day(s) per second",
        "",
        "// Every scalar arrives as [raw, normalized 0-1]:",
        "//   /phenology/day/activity, richness, biophony, geophony,",
        "//   anthrophony, ndsi, adi, aci, dawn",
        "// /phenology/diel/table carries 24 floats (a diel wavetable).",
    ]
    return _write_sc_score(phenology_timeline(calendar, config),
                           output_path, header)


def _write_sc_score(timeline: list[tuple[float, str, list]],
                    output_path: str, header: list[str]) -> str:
    """Shared .scd writer for event and phenology scores."""
    bundles = [
        f"  [{at:.4f}, [{_sc_string(addr)}, {_format_sc_args(args)}]]"
        for at, addr, args in timeline
    ]

    lines = [*header, "", "(", "var score = Score([", ",\n".join(bundles), "]);", ""]
    lines += [
        "// To play:        score.play;",
        '// To render NRT:  score.recordNRT(outputFilePath: "parliament_render.aiff");',
        ")",
    ]

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def write_osc_manifest(output_path: str, config: OSCConfig | None = None) -> str:
    """Write a human-readable OSC address map to hand to whoever patches this."""
    config = config or OSCConfig()
    ns = config.namespace.rstrip("/")
    pns = config.phenology_namespace.rstrip("/")

    lines = [
        "# OSC address map",
        "",
        f"Target: {config.host}:{config.port}",
        f"Query server (when enabled): {config.listen_host}:{config.listen_port}",
        "",
        "## Phenological calendar (primary payload)",
        "",
        f"{pns}/meta                 int n_days, str first_date, str last_date, float days_per_second",
        f"{pns}/range/<field>        float min, float max   (normalization used for cv)",
        f"{pns}/diel/table           24 floats 0-1          (diel activity wavetable)",
        f"{pns}/diel/peak_hour       int hour",
        f"{pns}/dawn_chorus/mean     float minutes after midnight",
        f"{pns}/day                  int index, str date, int day_of_year",
        f"{pns}/day/recordings       int",
        f"{pns}/day/events           int",
    ]
    lines += [
        f"{pns}/day/{field:<15} float raw, float cv (0-1)"
        for field in CV_FIELDS
    ]
    lines += [
        f"{pns}/day/dominant_role    str role",
        f"{pns}/day/role             str role, int count, float share   (repeated)",
        f"{pns}/day/hourly           24 ints (events per hour)",
        f"{pns}/event                str type, str date, int day_of_year, float magnitude",
        f"{pns}/end                  int 1",
        "",
        "## Acoustic events",
        "",
        f"{ns}/event               int 1 (bang)",
        f"{ns}/event/onset         float seconds into recording",
        f"{ns}/event/duration      float seconds",
        f"{ns}/event/role          str ecological role",
        f"{ns}/event/domain        str biophony|geophony|anthrophony|transition",
        f"{ns}/event/band          str dominant frequency band",
        f"{ns}/event/centroid      float Hz",
        f"{ns}/event/voct          float volts (centroid, 261.63Hz = 0V)",
        f"{ns}/event/flatness      float 0-1 (0=tonal, 1=noise)",
        f"{ns}/event/flux          float peak spectral flux",
        f"{ns}/event/confidence    float 0-1",
        f"{ns}/event/aci           float acoustic complexity",
        f"{ns}/event/ndsi          float -1..1",
        f"{ns}/event/bio           float bioacoustic index",
        f"{ns}/event/adi           float acoustic diversity",
        f"{ns}/habitat             str",
        f"{ns}/season              str",
        f"{ns}/temperature         float degrees C",
        f"{ns}/hour                int 0-23",
        f"{ns}/democracy_index     float Shannon entropy of role distribution",
        "",
        "## ILDA laser",
        "",
        "/ilda/color             int color index (from dominant band)",
        "/ilda/intensity         float 0-1 (confidence)",
        "/ilda/angle             float 0-1 (centroid)",
        "/ilda/speed             float 0-1 (flux)",
        "",
        "## Queries accepted by the OSC server",
        "",
        f"{pns}/query/meta         -> replies with the header burst",
        f"{pns}/query/day  [int]   -> replies with that day's frame",
        f"{pns}/query/date [str]   -> replies with that date's frame",
        f"{pns}/query/next         -> advances one day and replies",
        f"{pns}/query/events       -> replies with all phenological shifts",
        f"{pns}/query/reply_port [int] -> set the UDP port replies go to",
    ]

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


# --- live senders -----------------------------------------------------------

def _client(config: OSCConfig):
    from pythonosc.udp_client import SimpleUDPClient
    return SimpleUDPClient(config.host, config.port)


def send_messages(client, messages: list[tuple[str, list]]) -> None:
    """Send (address, args) pairs, unwrapping single-argument messages."""
    for addr, args in messages:
        client.send_message(addr, args[0] if len(args) == 1 else args)


def send_live_osc(events: list[dict], recording_meta: dict,
                  config: OSCConfig,
                  phenology_events: list[dict] | None = None) -> None:
    """
    Replay events in real time to the OSC target.

    Events are sent at their onset times relative to playback start.
    """
    client = _client(config)
    sorted_events = sorted(events, key=lambda e: e.get("onset_s", 0))
    start_time = time.time()

    print(f"OSC live playback -> {config.host}:{config.port}")
    print(f"Sending {len(sorted_events)} events...")

    for event in sorted_events:
        onset = event.get("onset_s", 0)
        target_time = start_time + onset
        now = time.time()
        if target_time > now:
            time.sleep(target_time - now)

        send_messages(client, build_event_osc_messages(event, recording_meta,
                                                       config.namespace))
        print(f"  [{onset:.1f}s] {event.get('role', '?')}")

    if phenology_events:
        for pheno_event in phenology_events:
            send_messages(client, build_phenology_event_messages(
                pheno_event, config.phenology_namespace))

    print("OSC playback complete.")


def stream_phenology(calendar: dict, config: OSCConfig | None = None) -> None:
    """
    Stream the phenological calendar to the OSC target in compressed time.

    One day of field recording becomes `1 / days_per_second` seconds of
    playback. With loop=True the season repeats until interrupted, which is the
    usual mode for an installation.
    """
    config = config or OSCConfig()
    frames = calendar.get("frames", [])
    if not frames:
        print("No phenological frames to stream (need recordings across >1 day).")
        return

    # Streaming often runs unattended with output redirected to a log.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass

    client = _client(config)
    timeline = phenology_timeline(calendar, config)
    span = timeline[-1][0] if timeline else 0.0

    print(f"Phenology stream -> {config.host}:{config.port}")
    print(f"  {len(frames)} days at {config.days_per_second} day/s "
          f"({span:.1f}s per pass){', looping' if config.loop else ''}")
    print("  Ctrl+C to stop.")

    try:
        while True:
            start = time.time()
            last_day = None
            for at, addr, args in timeline:
                wait = start + at - time.time()
                if wait > 0:
                    time.sleep(wait)
                client.send_message(addr, args[0] if len(args) == 1 else args)
                if addr.endswith("/day") and args and args[0] != last_day:
                    last_day = args[0]
                    label = args[1] if len(args) > 1 else last_day
                    print(f"  day {last_day}: {label}")
            if not config.loop:
                break
            print("  --- loop ---")
    except KeyboardInterrupt:
        print("\nPhenology stream stopped.")


def _sc_string(text: str) -> str:
    """Quote a string as a SuperCollider literal."""
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


# Kept for backward compatibility with earlier scripts.
addr_to_sc = _sc_string


def _format_sc_args(args: list) -> str:
    """Format args for SuperCollider syntax."""
    parts = []
    for a in args:
        if isinstance(a, bool):
            parts.append("1" if a else "0")
        elif isinstance(a, str):
            parts.append(_sc_string(a))
        elif isinstance(a, float):
            parts.append(f"{a:.6f}")
        elif isinstance(a, int):
            parts.append(str(a))
        else:
            parts.append(_sc_string(a))
    return ", ".join(parts)
