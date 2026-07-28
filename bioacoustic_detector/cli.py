"""
CLI entry point for the bioacoustic event detector.

Usage: python -m bioacoustic_detector.cli <WAV_FILE_OR_DIR> [options]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

from .config import Config, SpectralConfig, DetectorConfig, VideoConfig, OSCConfig
from .spectral import analyze
from .detector import detect_events, Event
from .classifier import classify_event, parliament_summary, Classification
from .indices import compute_all_indices
from .clipper import extract_all_clips
from .video import generate_all_videos
from .metadata import get_recording_metadata
from .report import generate_event_report, generate_summary_report
from .osc_output import (write_osc_bundle_file, generate_supercollider_score,
                         send_live_osc)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bioacoustic Event Detector — Parliament of the Living",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", help="WAV file or directory to process")
    parser.add_argument("-o", "--output-dir", default="./detected_events",
                        help="Output directory (default: ./detected_events)")
    parser.add_argument("--threshold", type=float, default=2.5,
                        help="Spectral flux threshold in MAD units (default: 2.5)")
    parser.add_argument("--pre-roll", type=float, default=20.0,
                        help="Seconds before event onset (default: 20)")
    parser.add_argument("--baseline-window", type=float, default=60.0,
                        help="Baseline window in seconds (default: 60)")
    parser.add_argument("--min-event-duration", type=float, default=2.0,
                        help="Minimum event duration in seconds (default: 2)")
    parser.add_argument("--max-freq", type=int, default=10000,
                        help="Max frequency Hz for analysis/video (default: 10000)")
    parser.add_argument("--no-video", action="store_true",
                        help="Skip spectrogram MP4 generation")
    parser.add_argument("--json-only", action="store_true",
                        help="Output JSON metadata only")

    # OSC options
    parser.add_argument("--osc-live", action="store_true",
                        help="Replay events as live OSC to target host")
    parser.add_argument("--osc-host", default="127.0.0.1",
                        help="OSC target host (default: 127.0.0.1)")
    parser.add_argument("--osc-port", type=int, default=57120,
                        help="OSC target port (default: 57120)")
    parser.add_argument("--no-osc", action="store_true",
                        help="Skip OSC/SuperCollider output")

    # Phenology
    parser.add_argument("--phenology", action="store_true",
                        help="Generate phenological calendar (requires multiple recordings)")

    return parser.parse_args(argv)


def find_wav_files(path: str) -> list[str]:
    """Find all WAV files in path (file or directory)."""
    p = Path(path)
    if p.is_file() and p.suffix.lower() == ".wav":
        return [str(p)]
    if p.is_dir():
        files = sorted(list(p.rglob("*.WAV")) + list(p.rglob("*.wav")))
        return [str(f) for f in files]
    return []


def process_single_file(wav_path: str, config: Config) -> dict:
    """
    Process a single WAV file through the full pipeline.

    Returns a result dict with all metadata, events, classifications, indices.
    """
    filename = Path(wav_path).name
    stem = Path(wav_path).stem
    file_output_dir = str(Path(config.output_dir) / stem)
    Path(file_output_dir).mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Processing: {filename}")
    print(f"{'='*60}")

    # 1. Read audio
    print("  Reading audio...")
    audio, sr = sf.read(wav_path, dtype="float64")
    if audio.ndim > 1:
        audio_mono = np.mean(audio, axis=1)
    else:
        audio_mono = audio
    duration_s = len(audio_mono) / sr
    print(f"  Duration: {duration_s:.1f}s, SR: {sr}Hz")

    # 2. Metadata
    print("  Extracting metadata...")
    recording_meta = get_recording_metadata(wav_path)
    recording_meta["duration_s"] = duration_s
    recording_meta["samplerate_hz"] = sr

    # 3. Spectral analysis
    print("  Computing spectral features...")
    spectral_result = analyze(audio_mono, sr, config.spectral)

    # 4. File-level acoustic indices
    print("  Computing acoustic indices...")
    file_indices = compute_all_indices(
        spectral_result["magnitude"], spectral_result["freqs"], config.spectral
    )

    # 5. Event detection
    print("  Detecting events...")
    events = detect_events(
        spectral_result["flux"],
        spectral_result["frame_times"],
        duration_s,
        config.detector,
    )
    print(f"  Found {len(events)} events")

    # 6. Classify events and compute per-event features
    print("  Classifying events...")
    events_data = []
    classifications = []
    prev_flux = None

    for i, event in enumerate(events):
        # Get mean spectral features for this event's frames
        f_start = event.onset_frame
        f_end = min(event.offset_frame + 1, spectral_result["magnitude"].shape[0])

        if f_end <= f_start:
            f_end = f_start + 1
        if f_end > spectral_result["magnitude"].shape[0]:
            continue

        event_mag = spectral_result["magnitude"][f_start:f_end]
        event_centroid = float(np.mean(spectral_result["centroid"][f_start:f_end]))
        event_flatness = float(np.mean(spectral_result["flatness"][f_start:f_end]))

        # Band energies for this event
        event_bands = {}
        for band_name, full_series in spectral_result["band_energies"].items():
            event_bands[band_name] = float(np.mean(full_series[f_start:f_end]))

        # Per-event indices
        event_indices = compute_all_indices(
            event_mag, spectral_result["freqs"], config.spectral
        )

        # Classify
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

        event_dict = {
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
            # Classification
            "role": classification.role,
            "domain": classification.domain,
            "confidence": round(classification.confidence, 3),
            "dominant_band": classification.dominant_band,
            "reasoning": classification.reasoning,
            # Indices
            **event_indices,
        }
        events_data.append(event_dict)

    # 7. Parliament summary
    parliament = parliament_summary(classifications)
    recording_meta["democracy_index"] = parliament.get("democracy_index", 0)

    # 8. Write events.json
    events_json = {
        "source_file": wav_path,
        "filename": filename,
        "duration_s": round(duration_s, 3),
        "sample_rate": sr,
        "recording_datetime": recording_meta["datetime"].isoformat() if recording_meta.get("datetime") else None,
        "habitat": recording_meta.get("habitat"),
        "season": recording_meta.get("season"),
        "temperature_c": recording_meta.get("temperature_c"),
        "file_indices": file_indices,
        "parliament": parliament,
        "n_events": len(events_data),
        "events": events_data,
    }

    json_path = str(Path(file_output_dir) / "events.json")
    Path(json_path).write_text(
        json.dumps(events_json, indent=2, default=str), encoding="utf-8"
    )
    print(f"  Wrote {json_path}")

    if config.json_only:
        return _build_result(wav_path, events_data, events_json, file_indices,
                             recording_meta, parliament, file_output_dir)

    # 9. Extract clips
    if events:
        print("  Extracting clips...")
        clip_paths = extract_all_clips(wav_path, events, file_output_dir)

        # Attach clip paths to events_data
        for ed, cp in zip(events_data, clip_paths):
            ed["clip_path"] = cp

        # 10. Generate spectrogram videos
        if not config.no_video:
            print("  Generating spectrogram videos...")
            rec_dt = recording_meta.get("datetime")
            location = recording_meta.get("habitat", "AudioMoth Recording")
            video_metas = []
            for ed in events_data:
                date_text = ""
                if rec_dt:
                    date_text = rec_dt.strftime("%d %B %Y %H:%M")
                role_label = ed["role"].replace("_", " ").title()
                label = f"{role_label} ({ed['confidence']:.0%}) | {ed['dominant_band']}"
                video_metas.append({
                    "location_text": location,
                    "date_text": date_text,
                    "classification_label": label,
                })

            video_paths = generate_all_videos(clip_paths, video_metas, config.video)
            for ed, vp in zip(events_data, video_paths):
                ed["video_path"] = vp
            n_ok = sum(1 for v in video_paths if v)
            print(f"  Generated {n_ok}/{len(video_paths)} videos")

    # 11. OSC output
    if not config.no_osc:
        print("  Generating OSC output...")
        osc_path = str(Path(file_output_dir) / "events.osc")
        write_osc_bundle_file(events_data, recording_meta, osc_path)

        scd_path = str(Path(file_output_dir) / "events_score.scd")
        generate_supercollider_score(events_data, recording_meta, scd_path)
        print(f"  Wrote {osc_path}")
        print(f"  Wrote {scd_path}")

        if config.osc.live:
            send_live_osc(events_data, recording_meta, config.osc)

    # 12. HTML report
    print("  Generating report...")
    report_path = str(Path(file_output_dir) / "report.html")
    generate_event_report(
        wav_path, events_data, parliament, file_indices,
        recording_meta, report_path,
    )
    print(f"  Wrote {report_path}")

    return _build_result(wav_path, events_data, events_json, file_indices,
                         recording_meta, parliament, file_output_dir,
                         report_path)


def _build_result(wav_path, events_data, events_json, file_indices,
                  recording_meta, parliament, output_dir,
                  report_path="") -> dict:
    """Build the result dict for a processed file."""
    return {
        "filename": Path(wav_path).name,
        "filepath": wav_path,
        "n_events": len(events_data),
        "events": events_data,
        "indices": file_indices,
        "habitat": recording_meta.get("habitat", ""),
        "season": recording_meta.get("season", ""),
        "datetime": recording_meta.get("datetime"),
        "parliament": parliament,
        "band_energies": {k: float(np.mean([e.get("band_energies", {}).get(k, 0) for e in events_data])) for k in ["geophony", "biophony_low", "biophony_mid", "biophony_high", "ultrasonic"]} if events_data else {},
        "ndsi": file_indices.get("ndsi", 0),
        "output_dir": output_dir,
        "report_path": report_path,
    }


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    # Build config from args
    config = Config(
        spectral=SpectralConfig(),
        detector=DetectorConfig(
            baseline_window_s=args.baseline_window,
            threshold_factor=args.threshold,
            pre_roll_s=args.pre_roll,
            min_event_duration_s=args.min_event_duration,
        ),
        video=VideoConfig(max_freq=args.max_freq),
        osc=OSCConfig(
            host=args.osc_host,
            port=args.osc_port,
            live=args.osc_live,
        ),
        output_dir=args.output_dir,
        no_video=args.no_video,
        json_only=args.json_only,
        no_osc=args.no_osc,
        phenology=args.phenology,
    )

    # Find WAV files
    wav_files = find_wav_files(args.input)
    if not wav_files:
        print(f"No WAV files found in: {args.input}")
        sys.exit(1)

    print(f"Found {len(wav_files)} WAV file(s)")
    Path(config.output_dir).mkdir(parents=True, exist_ok=True)

    # Process each file
    all_results = []
    all_classifications = []

    for wav_path in wav_files:
        result = process_single_file(wav_path, config)
        all_results.append(result)

    # Aggregate parliament across all files
    all_events = []
    for r in all_results:
        all_events.extend(r.get("events", []))

    # Build aggregate classifications for summary
    from .classifier import Classification
    all_cls = [
        Classification(
            role=e.get("role", "unknown"),
            domain=e.get("domain", "unknown"),
            confidence=e.get("confidence", 0),
            dominant_band=e.get("dominant_band", "unknown"),
            reasoning="",
        )
        for e in all_events
    ]
    aggregate_parliament = parliament_summary(all_cls)

    # Phenological calendar
    if config.phenology and len(all_results) > 1:
        print("\nGenerating phenological calendar...")
        from .phenology import build_phenological_calendar, generate_phenology_html

        calendar = build_phenological_calendar(all_results)

        cal_json_path = str(Path(config.output_dir) / "phenological_calendar.json")
        Path(cal_json_path).write_text(
            json.dumps(calendar, indent=2, default=str), encoding="utf-8"
        )
        print(f"  Wrote {cal_json_path}")

        cal_html_path = str(Path(config.output_dir) / "phenological_calendar.html")
        generate_phenology_html(calendar, cal_html_path)
        print(f"  Wrote {cal_html_path}")

        # Feed phenological events to combined OSC score
        if not config.no_osc:
            pheno_events = calendar.get("phenological_events", [])
            combined_scd = str(Path(config.output_dir) / "parliament_osc_score.scd")
            generate_supercollider_score(
                all_events,
                {"filename": "combined", "habitat": "multiple", "season": "multiple",
                 "datetime": None, "temperature_c": None, "democracy_index":
                 aggregate_parliament.get("democracy_index", 0)},
                combined_scd,
                phenology_events=pheno_events,
            )
            print(f"  Wrote {combined_scd}")

    # Summary report for batch processing
    if len(all_results) > 1:
        summary_path = str(Path(config.output_dir) / "summary_report.html")
        generate_summary_report(all_results, aggregate_parliament, summary_path)
        print(f"\nWrote batch summary: {summary_path}")

    # Final summary
    total_events = sum(r["n_events"] for r in all_results)
    print(f"\n{'='*60}")
    print(f"Complete: {len(all_results)} file(s), {total_events} events detected")
    print(f"Parliament democracy index: {aggregate_parliament.get('democracy_index', 0):.3f}")
    print(f"Output: {config.output_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
