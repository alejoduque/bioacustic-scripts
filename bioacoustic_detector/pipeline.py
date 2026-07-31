"""
The processing pipeline, shared by the CLI and the wizard.

One recording:
    audio -> metadata -> spectral features -> events -> classification
          -> filtered selection -> clips -> per-event video/poster/gif
          -> per-type reels -> events.json -> OSC -> HTML report

A batch adds the cross-recording layer that the whole toolkit exists for:
    results -> phenological calendar -> OSC score/stream -> gallery -> summary
"""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import soundfile as sf

from . import store
from .classifier import Classification, classify_event, parliament_summary
from .clipper import extract_clips, select_events
from .config import Config, VideoConfig
from .detector import Event, detect_events
from .gallery import generate_gallery
from .indices import compute_all_indices
from .media import have_ffmpeg
from .metadata import get_recording_metadata
from .osc_output import (generate_phenology_supercollider_score,
                         generate_supercollider_score, send_live_osc,
                         write_osc_bundle_file, write_osc_manifest,
                         write_phenology_osc_file)
from .phenology import (build_phenological_calendar, generate_phenology_html,
                        write_phenology_csv)
from .report import generate_event_report, generate_summary_report
from .spectral import (MIN_PERIODICITY_WINDOW_S, analyze,
                       event_band_features)
from .video import build_event_type_reels, render_all_clips

def video_config_for(config: Config, sample_rate: int) -> VideoConfig:
    """
    Frame the spectrogram for one recording's sample rate.

    In the audible default the top of the plot stays at max_freq (10 kHz), which
    is where nearly all bird, frog and insect energy lives — stretching the axis
    to Nyquist would squash the interesting part into the bottom sliver.

    In ultrasonic mode the axis has to reach Nyquist or the bats are simply not
    on the picture, and it switches to a logarithmic frequency scale so that
    0-10 kHz still occupies a readable share of a 0-96 kHz plot.
    """
    nyquist = sample_rate // 2
    if not config.ultrasonic:
        return replace(config.video, max_freq=min(config.video.max_freq, nyquist))
    return replace(config.video, max_freq=nyquist, freq_scale="log")


def find_wav_files(paths: str | list[str]) -> list[str]:
    """
    Find all WAV files in one or more paths (files or directories).

    Accepts a list so a shell glob (`*.WAV`) works as well as a directory.
    Deduplicated and sorted by name.
    """
    if isinstance(paths, str):
        paths = [paths]

    found: set[Path] = set()
    for raw in paths:
        p = Path(raw)
        if p.is_file() and p.suffix.lower() == ".wav":
            found.add(p.resolve())
        elif p.is_dir():
            found.update(f.resolve() for f in p.rglob("*")
                         if f.suffix.lower() == ".wav")
    return [str(f) for f in sorted(found)]


# --- single recording -------------------------------------------------------

def classify_all(events: list[Event], spectral_result: dict,
                 recording_meta: dict, config: Config
                 ) -> tuple[list[tuple[Event, dict]], list[Classification]]:
    """
    Classify every detected event.

    Returns (Event, event_dict) pairs plus the Classification objects. Keeping
    the Event beside its dict is what guarantees clips, videos and metadata stay
    aligned — an earlier version zipped two separately-filtered lists and could
    attach the wrong clip to an event.
    """
    magnitude = spectral_result["magnitude"]
    n_frames = magnitude.shape[0]

    pairs: list[tuple[Event, dict]] = []
    classifications: list[Classification] = []
    prev_flux = None

    for i, event in enumerate(events):
        f_start = min(event.onset_frame, n_frames - 1)
        f_end = min(event.offset_frame + 1, n_frames)
        if f_end <= f_start:
            f_end = min(f_start + 1, n_frames)
        if f_end <= f_start:
            continue

        event_mag = magnitude[f_start:f_end]
        event_centroid = float(np.mean(spectral_result["centroid"][f_start:f_end]))
        event_flatness = float(np.mean(spectral_result["flatness"][f_start:f_end]))

        event_bands = {
            name: float(np.mean(series[f_start:f_end]))
            for name, series in spectral_result["band_energies"].items()
        }

        event_indices = compute_all_indices(event_mag, spectral_result["freqs"],
                                            config.spectral)

        # Within-band and temporal features, computed on the event's dominant
        # band. The global centroid/flatness cannot tell a low-frequency chorus
        # from low-frequency weather; these describe the band the event actually
        # occupies, and how its energy is organised in time.
        dominant = max(event_bands, key=event_bands.get) if event_bands else ""
        band_feats = {}
        if dominant and dominant in config.spectral.bands:
            frame_rate = spectral_result["sr"] / spectral_result["hop_size"]
            # Widen a short event to a context window for the temporal features
            # only; call rate belongs to the sequence, not to one call.
            need = int(MIN_PERIODICITY_WINDOW_S * frame_rate)
            if (f_end - f_start) < need:
                pad = (need - (f_end - f_start)) // 2
                c0, c1 = max(0, f_start - pad), min(n_frames, f_end + pad)
            else:
                c0, c1 = f_start, f_end
            band_feats = event_band_features(
                event_mag, spectral_result["freqs"],
                config.spectral.bands[dominant], frame_rate,
                context_mag=magnitude[c0:c1])

        classification = classify_event(
            event.onset_s, event.offset_s,
            event_centroid, event_flatness, event.peak_flux,
            event_bands,
            recording_datetime=recording_meta.get("datetime"),
            prev_event_flux=prev_flux,
            config=config.spectral,
        )
        classifications.append(classification)
        prev_flux = event.peak_flux

        pairs.append((event, {
            "event_index": i + 1,
            "onset_s": round(event.onset_s, 3),
            "offset_s": round(event.offset_s, 3),
            "clip_start_s": round(event.clip_start_s, 3),
            "clip_end_s": round(event.clip_end_s, 3),
            "duration_s": round(event.offset_s - event.onset_s, 3),
            "peak_flux": round(event.peak_flux, 4),
            "mean_flux": round(event.mean_flux, 4),
            "centroid": round(event_centroid, 1),
            "flatness": round(event_flatness, 4),
            "band_energies": {k: round(v, 4) for k, v in event_bands.items()},
            "role": classification.role,
            "domain": classification.domain,
            "confidence": round(classification.confidence, 3),
            "dominant_band": classification.dominant_band,
            "reasoning": classification.reasoning,
            **band_feats,
            **event_indices,
        }))

    return pairs, classifications


def process_single_file(wav_path: str, config: Config) -> dict:
    """Run one WAV file through the full pipeline and return its result dict."""
    filename = Path(wav_path).name
    stem = Path(wav_path).stem
    file_output_dir = Path(config.output_dir) / stem
    file_output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"Processing: {filename}")
    print(f"{'=' * 60}")

    print("  Reading audio...")
    audio, sr = sf.read(wav_path, dtype="float64")
    audio_mono = np.mean(audio, axis=1) if audio.ndim > 1 else audio
    duration_s = len(audio_mono) / sr
    print(f"  Duration: {duration_s:.1f}s, SR: {sr}Hz")

    target = config.spectral.target_sr
    if not config.ultrasonic and target and sr > 2 * target:
        print(f"  ! This recording carries content up to {sr // 2000} kHz, but "
              f"analysis downsamples to {target // 1000} kHz.")
        print(f"    Everything above {target // 2000} kHz — bat echolocation, "
              f"high katydids — is discarded.")
        print("    Re-run with --ultrasonic to analyse at the native rate.")
    if config.ultrasonic:
        freq_res, time_res = config.spectral.resolution(sr)
        print(f"  Ultrasonic mode: native {sr}Hz, "
              f"{freq_res:.0f}Hz / {time_res:.1f}ms resolution")

    print("  Extracting metadata...")
    recording_meta = get_recording_metadata(wav_path)
    recording_meta["duration_s"] = duration_s
    recording_meta["samplerate_hz"] = sr

    print("  Computing spectral features...")
    spectral_result = analyze(audio_mono, sr, config.spectral)

    print("  Computing acoustic indices...")
    file_indices = compute_all_indices(spectral_result["magnitude"],
                                       spectral_result["freqs"], config.spectral)

    print("  Detecting events...")
    events = detect_events(spectral_result["flux"], spectral_result["frame_times"],
                           duration_s, config.detector)
    print(f"  Found {len(events)} events")

    print("  Classifying events...")
    pairs, classifications = classify_all(events, spectral_result,
                                          recording_meta, config)
    events_data = [data for _, data in pairs]

    # The parliament census covers every detected event, whether or not the
    # user asked for a clip of it.
    parliament = parliament_summary(classifications)
    recording_meta["democracy_index"] = parliament.get("democracy_index", 0)
    _print_role_breakdown(parliament)

    selected = pairs
    if not config.json_only:
        selected = select_events(pairs, config.clip)
        if len(selected) != len(pairs):
            print(f"  Clip filter kept {len(selected)}/{len(pairs)} events")

    reels: dict[str, str] = {}
    if not config.json_only and selected:
        print("  Extracting clips...")
        clip_paths = extract_clips(wav_path, selected, str(file_output_dir),
                                   config.clip)
        for (_, data), clip_path in zip(selected, clip_paths):
            data["clip_path"] = clip_path

        render_video = config.clip.make_video and not config.no_video
        wants_media = render_video or config.clip.make_poster or config.clip.make_gif
        if wants_media and not have_ffmpeg():
            print("  ! ffmpeg not found — skipping video/poster rendering.")
            print("    Install it (brew install ffmpeg) and re-run to get clips on video.")
        elif wants_media:
            print("  Rendering event media...")
            clip_config = config.clip
            if not render_video:
                clip_config = _without_video(clip_config)
            renders = render_all_clips(clip_paths, [d for _, d in selected],
                                       recording_meta,
                                       video_config_for(config, sr), clip_config)
            for (_, data), render in zip(selected, renders):
                data.update(render.as_dict())
                for problem in render.errors:
                    print(f"    ! {Path(data['clip_path']).name}: {problem}")

            if config.clip.make_reels and render_video:
                print("  Building per-type reels...")
                reels = build_event_type_reels([d for _, d in selected],
                                               str(file_output_dir), config.clip)

    result = _build_result(wav_path, events_data, file_indices, recording_meta,
                           parliament, str(file_output_dir), duration_s, sr,
                           reels, tuple(config.spectral.bands))

    json_path = store.write_result(result, str(file_output_dir))
    print(f"  Wrote {json_path}")

    if config.json_only:
        return result

    if not config.no_osc:
        osc_path = str(file_output_dir / "events.osc")
        write_osc_bundle_file(events_data, recording_meta, osc_path,
                              config=config.osc)
        scd_path = str(file_output_dir / "events_score.scd")
        generate_supercollider_score(events_data, recording_meta, scd_path,
                                     config=config.osc)
        print(f"  Wrote {osc_path}")
        print(f"  Wrote {scd_path}")

        if config.osc.live:
            send_live_osc(events_data, recording_meta, config.osc)

    print("  Generating report...")
    report_path = str(file_output_dir / "report.html")
    generate_event_report(wav_path, events_data, parliament, file_indices,
                          recording_meta, report_path)
    result["report_path"] = report_path
    store.write_result(result, str(file_output_dir))
    print(f"  Wrote {report_path}")

    return result


def _without_video(clip_config):
    """Copy of a ClipConfig with video (and therefore reels) disabled."""
    from dataclasses import replace
    return replace(clip_config, make_video=False, make_reels=False)


def _print_role_breakdown(parliament: dict) -> None:
    roles = parliament.get("role_counts", {})
    if not roles:
        return
    listing = ", ".join(f"{role} x{count}" for role, count
                        in sorted(roles.items(), key=lambda kv: -kv[1]))
    print(f"  Voices: {listing}")


def _build_result(wav_path: str, events_data: list[dict], file_indices: dict,
                  recording_meta: dict, parliament: dict, output_dir: str,
                  duration_s: float, sample_rate: int,
                  reels: dict[str, str],
                  band_names: tuple = ()) -> dict:
    """Build the in-memory result dict for a processed recording."""
    band_energies = {}
    if events_data:
        # Band names come from the active table, so an ultrasonic run carries
        # its bat bands through to the calendar instead of dropping them.
        band_energies = {
            band: float(np.mean([e.get("band_energies", {}).get(band, 0)
                                 for e in events_data]))
            for band in band_names
        }

    return {
        "filename": Path(wav_path).name,
        "filepath": wav_path,
        "duration_s": round(duration_s, 3),
        "sample_rate": sample_rate,
        "datetime": recording_meta.get("datetime"),
        "habitat": recording_meta.get("habitat", ""),
        "season": recording_meta.get("season", "") or "",
        "temperature_c": recording_meta.get("temperature_c"),
        "indices": file_indices,
        "band_energies": band_energies,
        "parliament": parliament,
        "n_events": len(events_data),
        "n_clips": sum(1 for e in events_data if e.get("clip_path")),
        "events": events_data,
        "ndsi": file_indices.get("ndsi", 0),
        "output_dir": output_dir,
        "report_path": "",
        "reels": reels,
    }


# --- batch layer ------------------------------------------------------------

def aggregate_parliament(results: list[dict]) -> dict:
    """Parliament census across every recording in a batch."""
    all_events = [e for r in results for e in r.get("events", [])]
    return parliament_summary([
        Classification(
            role=e.get("role", "unknown"),
            domain=e.get("domain", "unknown"),
            confidence=e.get("confidence", 0),
            dominant_band=e.get("dominant_band", "unknown"),
            reasoning="",
        )
        for e in all_events
    ])


def build_phenology(results: list[dict], config: Config) -> dict:
    """
    Build and write the phenological calendar plus its OSC exports.

    Returns {"calendar", "json", "html", "csv", "osc", "scd"} (paths may be "").
    """
    out_dir = Path(config.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    dated = [r for r in results if r.get("datetime")]
    if len(dated) < len(results):
        print(f"  Note: {len(results) - len(dated)} recording(s) have no "
              f"timestamp and are excluded from the calendar.")

    calendar = build_phenological_calendar(results, config.phenology)
    written = {"calendar": calendar, "json": "", "html": "", "csv": "",
               "osc": "", "scd": ""}

    json_path = out_dir / store.CALENDAR_FILENAME
    json_path.write_text(json.dumps(calendar, indent=2, default=str),
                         encoding="utf-8")
    written["json"] = str(json_path)
    print(f"  Wrote {json_path}")

    html_path = out_dir / "phenological_calendar.html"
    generate_phenology_html(calendar, str(html_path))
    written["html"] = str(html_path)
    print(f"  Wrote {html_path}")

    if config.phenology.write_csv:
        csv_path = out_dir / "phenological_series.csv"
        write_phenology_csv(calendar, str(csv_path))
        written["csv"] = str(csv_path)
        print(f"  Wrote {csv_path}")

    if not config.no_osc:
        osc_path = out_dir / "phenology.osc"
        write_phenology_osc_file(calendar, str(osc_path), config.osc)
        written["osc"] = str(osc_path)
        print(f"  Wrote {osc_path}")

        scd_path = out_dir / "phenology_score.scd"
        generate_phenology_supercollider_score(calendar, str(scd_path), config.osc)
        written["scd"] = str(scd_path)
        print(f"  Wrote {scd_path}")

        manifest = out_dir / "osc_address_map.txt"
        write_osc_manifest(str(manifest), config.osc)
        print(f"  Wrote {manifest}")

    n_days = len(calendar.get("frames", []))
    n_shifts = len(calendar.get("phenological_events", []))
    print(f"  Calendar: {n_days} day(s), {n_shifts} phenological shift(s)")

    return written


def build_gallery(results: list[dict], config: Config,
                  phenology_link: str = "") -> str:
    """Write the event-clip gallery for a batch. Returns the path or ""."""
    reels: dict[str, str] = {}
    for result in results:
        reels.update(result.get("reels", {}))

    if not any(e.get("clip_path") or e.get("video_path")
               for r in results for e in r.get("events", [])):
        return ""

    path = str(Path(config.output_dir) / "gallery.html")
    generate_gallery(results, path, reels=reels, phenology_link=phenology_link)
    print(f"  Wrote {path}")
    return path


def run_batch(inputs: str | list[str], config: Config) -> dict:
    """
    Process every WAV under `inputs`, then build the cross-recording outputs.

    Returns {"results", "parliament", "phenology", "gallery", "summary"}.
    """
    wav_files = find_wav_files(inputs)
    if not wav_files:
        listing = inputs if isinstance(inputs, str) else ", ".join(inputs)
        raise FileNotFoundError(f"No WAV files found in: {listing}")

    print(f"Found {len(wav_files)} WAV file(s)")
    Path(config.output_dir).mkdir(parents=True, exist_ok=True)

    results = [process_single_file(wav, config) for wav in wav_files]
    parliament = aggregate_parliament(results)

    outcome = {"results": results, "parliament": parliament,
               "phenology": {}, "gallery": "", "summary": ""}

    if config.build_phenology:
        print("\nGenerating phenological calendar...")
        if len(results) < 2:
            print("  Only one recording — the calendar needs several to compare.")
        outcome["phenology"] = build_phenology(results, config)

    if config.build_gallery and not config.json_only:
        print("\nBuilding event gallery...")
        outcome["gallery"] = build_gallery(
            results, config, outcome["phenology"].get("html", ""))

    if len(results) > 1:
        summary_path = str(Path(config.output_dir) / "summary_report.html")
        generate_summary_report(results, parliament, summary_path,
                                gallery_path=outcome["gallery"],
                                phenology_path=outcome["phenology"].get("html", ""))
        outcome["summary"] = summary_path
        print(f"\nWrote batch summary: {summary_path}")

    _print_final_summary(results, parliament, config, outcome)
    return outcome


def _print_final_summary(results: list[dict], parliament: dict, config: Config,
                         outcome: dict) -> None:
    total_events = sum(r["n_events"] for r in results)
    total_clips = sum(r.get("n_clips", 0) for r in results)
    print(f"\n{'=' * 60}")
    print(f"Complete: {len(results)} file(s), {total_events} events, "
          f"{total_clips} clip(s)")
    print(f"Parliament democracy index: "
          f"{parliament.get('democracy_index', 0):.3f}")
    print(f"Output: {config.output_dir}")
    for label, key in (("Gallery", "gallery"), ("Summary", "summary")):
        if outcome.get(key):
            print(f"{label}: {outcome[key]}")
    if outcome.get("phenology", {}).get("html"):
        print(f"Calendar: {outcome['phenology']['html']}")
    print(f"{'=' * 60}")
