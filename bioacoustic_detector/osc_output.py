"""
OSC (Open Sound Control) output for detected events.

Two modes:
- Batch: write OSC bundle file + SuperCollider score (.scd)
- Live/playback: replay events in real-time to a configurable OSC target

Designed for Eurorack modular synthesis, ILDA laser control,
SuperCollider, and other OSC-capable instruments.

OSC address namespace: /parliament/event/*, /phenology/*, /ilda/*
"""

import json
import math
import time
from pathlib import Path

from .config import OSCConfig


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


def build_event_osc_messages(event: dict, recording_meta: dict) -> list[tuple[str, list]]:
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

    # Acoustic indices
    aci = event.get("aci", 0.0)
    ndsi = event.get("ndsi", 0.0)
    bio = event.get("bio", 0.0)
    adi = event.get("adi", 0.0)

    # Recording context
    habitat = recording_meta.get("habitat", "unknown")
    season = recording_meta.get("season", "unknown")
    temp = recording_meta.get("temperature_c", 0.0) or 0.0
    dt = recording_meta.get("datetime")
    hour = dt.hour if dt else 0
    democracy = recording_meta.get("democracy_index", 0.0)

    messages = [
        ("/parliament/event", [1]),  # bang
        ("/parliament/event/onset", [float(onset)]),
        ("/parliament/event/duration", [float(duration)]),
        ("/parliament/event/role", [str(role)]),
        ("/parliament/event/domain", [str(domain)]),
        ("/parliament/event/band", [str(band)]),
        ("/parliament/event/centroid", [float(centroid)]),
        ("/parliament/event/flatness", [float(flatness)]),
        ("/parliament/event/flux", [float(flux)]),
        ("/parliament/event/confidence", [float(confidence)]),
        ("/parliament/event/aci", [float(aci)]),
        ("/parliament/event/ndsi", [float(ndsi)]),
        ("/parliament/event/bio", [float(bio)]),
        ("/parliament/event/adi", [float(adi)]),
        ("/parliament/habitat", [str(habitat)]),
        ("/parliament/season", [str(season)]),
        ("/parliament/temperature", [float(temp)]),
        ("/parliament/hour", [int(hour)]),
        ("/parliament/democracy_index", [float(democracy)]),
        # ILDA mappings
        ("/ilda/color", [ILDA_BAND_COLORS.get(band, 0)]),
        ("/ilda/intensity", [float(confidence)]),
        ("/ilda/angle", [float(min(centroid / 10000.0, 1.0))]),
        ("/ilda/speed", [float(min(flux / 100.0, 1.0))]),
    ]

    return messages


def build_phenology_osc_messages(pheno_event: dict) -> list[tuple[str, list]]:
    """Build OSC messages for a phenological event."""
    return [
        ("/phenology/event", [1]),
        ("/phenology/type", [str(pheno_event.get("type", "unknown"))]),
        ("/phenology/day_of_year", [int(pheno_event.get("day_of_year", 0))]),
    ]


def build_dawn_chorus_message(dawn: dict) -> list[tuple[str, list]]:
    """Build OSC message for dawn chorus timing."""
    return [
        ("/phenology/dawn_chorus_time", [float(dawn.get("onset_minutes", 0))]),
    ]


def write_osc_bundle_file(events: list[dict], recording_meta: dict,
                          output_path: str,
                          phenology_events: list[dict] | None = None) -> str:
    """
    Write all OSC messages to a text-based bundle file.

    Format: one line per message, tab-separated:
    timestamp_s<TAB>address<TAB>arg1<TAB>arg2<TAB>...
    """
    lines = []

    for event in events:
        onset = event.get("onset_s", 0)
        messages = build_event_osc_messages(event, recording_meta)
        for addr, args in messages:
            arg_strs = [str(a) for a in args]
            lines.append(f"{onset:.4f}\t{addr}\t" + "\t".join(arg_strs))

    if phenology_events:
        for pe in phenology_events:
            messages = build_phenology_osc_messages(pe)
            for addr, args in messages:
                arg_strs = [str(a) for a in args]
                lines.append(f"0.0000\t{addr}\t" + "\t".join(arg_strs))

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def generate_supercollider_score(events: list[dict], recording_meta: dict,
                                 output_path: str,
                                 phenology_events: list[dict] | None = None) -> str:
    """
    Generate a SuperCollider Score (.scd) file.

    Format compatible with Score.newFromFile and NRT rendering.
    Each event becomes a timed OSC bundle.
    """
    lines = [
        "// SuperCollider Score — Parliament of the Living",
        "// Generated by Bioacoustic Event Detector",
        f"// Source: {recording_meta.get('filename', 'unknown')}",
        f"// Habitat: {recording_meta.get('habitat', 'unknown')}",
        "",
        "// Eurorack mapping notes:",
        "//   centroid -> V/Oct pitch CV (log-scaled from 261.63Hz = 0V)",
        "//   flux -> gate/trigger intensity",
        "//   flatness -> timbre CV (0=tonal, 1=noise)",
        "//   NDSI -> bipolar CV (-5V to +5V: -1=anthrophony, +1=biophony)",
        "",
        "(",
        "var score = Score([",
    ]

    bundles = []
    for event in events:
        onset = event.get("onset_s", 0)
        messages = build_event_osc_messages(event, recording_meta)
        for addr, args in messages:
            args_sc = _format_sc_args(args)
            bundles.append(f"  [{onset:.4f}, [{addr_to_sc(addr)}, {args_sc}]]")

    if phenology_events:
        for pe in phenology_events:
            messages = build_phenology_osc_messages(pe)
            for addr, args in messages:
                args_sc = _format_sc_args(args)
                bundles.append(f"  [0.0, [{addr_to_sc(addr)}, {args_sc}]]")

    lines.append(",\n".join(bundles))
    lines.extend([
        "]);",
        "",
        "// To play: score.play;",
        "// To render NRT: score.recordNRT(outputFilePath: \"parliament_render.aiff\");",
        "// To load from file: Score.newFromFile(thisProcess.nowExecutingPath.dirname +/+ \"events_score.scd\");",
        ")",
    ])

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def send_live_osc(events: list[dict], recording_meta: dict,
                  config: OSCConfig,
                  phenology_events: list[dict] | None = None) -> None:
    """
    Replay events in real-time to OSC target.

    Events are sent at their onset times relative to playback start.
    """
    from pythonosc.udp_client import SimpleUDPClient

    client = SimpleUDPClient(config.host, config.port)

    # Sort events by onset
    sorted_events = sorted(events, key=lambda e: e.get("onset_s", 0))
    start_time = time.time()

    print(f"OSC live playback -> {config.host}:{config.port}")
    print(f"Sending {len(sorted_events)} events...")

    for event in sorted_events:
        onset = event.get("onset_s", 0)
        # Wait until it's time
        target_time = start_time + onset
        now = time.time()
        if target_time > now:
            time.sleep(target_time - now)

        messages = build_event_osc_messages(event, recording_meta)
        for addr, args in messages:
            if len(args) == 1:
                client.send_message(addr, args[0])
            else:
                client.send_message(addr, args)

        role = event.get("role", "?")
        print(f"  [{onset:.1f}s] {role}")

    # Send phenological events at the end
    if phenology_events:
        for pe in phenology_events:
            messages = build_phenology_osc_messages(pe)
            for addr, args in messages:
                if len(args) == 1:
                    client.send_message(addr, args[0])
                else:
                    client.send_message(addr, args)

    print("OSC playback complete.")


def addr_to_sc(addr: str) -> str:
    """Convert OSC address to SuperCollider string literal."""
    return f'"{addr}"'


def _format_sc_args(args: list) -> str:
    """Format args for SuperCollider syntax."""
    parts = []
    for a in args:
        if isinstance(a, str):
            parts.append(f'"{a}"')
        elif isinstance(a, float):
            parts.append(f"{a:.6f}")
        elif isinstance(a, int):
            parts.append(str(a))
        else:
            parts.append(f'"{a}"')
    return ", ".join(parts)
