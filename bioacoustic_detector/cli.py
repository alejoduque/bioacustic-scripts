"""
CLI entry point for the bioacoustic toolkit.

    python -m bioacoustic_detector.cli <subcommand> [options]

Subcommands:
    detect      analyse recordings -> event clips, videos, OSC, reports
    phenology   build/refresh the phenological calendar and its OSC exports
    osc         export, stream or serve OSC (events and phenology)
    gallery     rebuild the event-clip gallery from existing results
    media       whole-file spectrogram, video splitting, video -> GIF
    metadata    AudioMoth metadata report (delegates to audiomoth_processing.sh)
    doctor      check tooling and report what is available
    wizard      interactive, guided front-end to all of the above

Passing a path as the first argument is shorthand for `detect <path>`, so
`./detect_events.sh recording.WAV --threshold 1.5` keeps working.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from . import store
from .classifier import ROLES
from .config import (SENSITIVITY_PRESETS, ClipConfig, Config, DetectorConfig,
                     OSCConfig, PhenologyConfig, SpectralConfig, VideoConfig,
                     apply_sensitivity, apply_ultrasonic)

REPO_ROOT = Path(__file__).resolve().parent.parent
SUBCOMMANDS = ("detect", "phenology", "osc", "gallery", "media", "metadata",
               "doctor", "wizard")
DOMAINS = ("biophony", "geophony", "anthrophony", "transition")


# --- argument parsing -------------------------------------------------------

def _csv_list(value: str) -> tuple:
    return tuple(v.strip() for v in value.split(",") if v.strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bioacoustic_detector",
        description="Bioacoustic toolkit — Parliament of the Living",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run with no arguments, or `wizard`, for the guided front-end.",
    )
    sub = parser.add_subparsers(dest="command")

    _add_detect_parser(sub)
    _add_phenology_parser(sub)
    _add_osc_parser(sub)
    _add_gallery_parser(sub)
    _add_media_parser(sub)
    _add_metadata_parser(sub)
    sub.add_parser("doctor", help="check ffmpeg/python/deps and report status")
    sub.add_parser("wizard", help="interactive guided front-end")

    return parser


def _add_detect_parser(sub) -> None:
    p = sub.add_parser(
        "detect", help="analyse recordings and produce event clips",
        description="Detect acoustic events and cut a video clip for each one.")
    p.add_argument("inputs", nargs="+",
                   help="WAV files and/or directories to process")
    p.add_argument("-o", "--output-dir", default="./detected_events",
                   help="Output directory (default: ./detected_events)")

    d = p.add_argument_group("detection")
    d.add_argument("--sensitivity", choices=sorted(SENSITIVITY_PRESETS),
                   help="Preset that sets threshold/duration/merge together")
    d.add_argument("--threshold", type=float,
                   help="Spectral flux threshold in MAD units (default: 2.5)")
    d.add_argument("--baseline-window", type=float, default=60.0,
                   help="Adaptive baseline window in seconds (default: 60)")
    d.add_argument("--min-event-duration", type=float,
                   help="Minimum event duration in seconds (default: 2)")
    d.add_argument("--merge-gap", type=float,
                   help="Merge events closer than this many seconds (default: 5)")
    d.add_argument("--pre-roll", type=float, default=20.0,
                   help="Seconds of context before onset (default: 20)")
    d.add_argument("--post-roll", type=float, default=10.0,
                   help="Seconds of context after offset (default: 10)")
    d.add_argument("--max-clip-duration", type=float, default=300.0,
                   help="Cap on clip length in seconds (default: 300)")
    d.add_argument("--ultrasonic", action="store_true",
                   help="Analyse at the recorder's native rate and extend the "
                        "bands to cover bat echolocation. Needed for AudioMoth "
                        "recordings made above 48kHz; without it everything "
                        "above 24kHz is discarded.")

    s = p.add_argument_group("event selection")
    s.add_argument("--roles", type=_csv_list, default=(),
                   help="Only clip these ecological roles (comma-separated)")
    s.add_argument("--domains", type=_csv_list, default=(),
                   help=f"Only clip these domains: {', '.join(DOMAINS)}")
    s.add_argument("--min-confidence", type=float, default=0.0,
                   help="Skip classifications below this confidence (0-1)")

    m = p.add_argument_group("media")
    m.add_argument("--max-freq", type=int, default=10000,
                   help="Max frequency Hz for spectrogram renders (default: 10000)")
    m.add_argument("--organize-by", choices=("role", "domain", "flat"),
                   default="role",
                   help="Clip directory layout (default: role)")
    m.add_argument("--no-video", action="store_true",
                   help="Skip spectrogram MP4 generation")
    m.add_argument("--no-poster", action="store_true",
                   help="Skip static spectrogram PNG/thumbnail generation")
    m.add_argument("--gif", action="store_true",
                   help="Also render a looping GIF per clip")
    m.add_argument("--no-reels", action="store_true",
                   help="Skip the concatenated one-video-per-event-type reels")
    m.add_argument("--no-style-by-domain", action="store_true",
                   help="Use one colormap for every event type")
    m.add_argument("--no-gallery", action="store_true",
                   help="Skip the HTML event gallery")
    m.add_argument("--json-only", action="store_true",
                   help="Output JSON metadata only (no clips, media or reports)")

    o = p.add_argument_group("OSC")
    o.add_argument("--osc-live", action="store_true",
                   help="Replay events as live OSC to the target host")
    o.add_argument("--osc-host", default="127.0.0.1",
                   help="OSC target host (default: 127.0.0.1)")
    o.add_argument("--osc-port", type=int, default=57120,
                   help="OSC target port (default: 57120)")
    o.add_argument("--no-osc", action="store_true",
                   help="Skip OSC/SuperCollider output")

    ph = p.add_argument_group("phenology")
    ph.add_argument("--phenology", action="store_true",
                    help="Build the phenological calendar (needs several recordings)")
    ph.add_argument("--days-per-second", type=float, default=1.0,
                    help="Calendar playback rate for OSC exports (default: 1)")
    ph.add_argument("--no-csv", action="store_true",
                    help="Skip the phenological CSV export")


def _add_phenology_parser(sub) -> None:
    p = sub.add_parser(
        "phenology", help="build the phenological calendar and OSC exports",
        description="Build the calendar from an output directory produced by "
                    "`detect`, or from recordings (analysed in metadata-only mode).")
    p.add_argument("input", help="Output directory with events.json files, "
                                 "or a directory of recordings")
    p.add_argument("-o", "--output-dir", default="",
                   help="Where to write the calendar (default: alongside results)")
    p.add_argument("--reanalyze", action="store_true",
                   help="Re-run detection even if events.json files exist")
    p.add_argument("--days-per-second", type=float, default=1.0,
                   help="Calendar playback rate for OSC exports (default: 1)")
    p.add_argument("--threshold", type=float, default=2.5,
                   help="Detection threshold when re-analysing (default: 2.5)")
    p.add_argument("--no-csv", action="store_true", help="Skip the CSV export")
    p.add_argument("--no-osc", action="store_true", help="Skip OSC exports")


def _add_osc_parser(sub) -> None:
    p = sub.add_parser(
        "osc", help="export, stream or serve OSC",
        description="Everything OSC. `phenology` is the main mode: it replays a "
                    "season of recordings as a time-compressed control stream.")
    p.add_argument("mode", choices=("export", "phenology", "events", "serve", "map"),
                   help="export: write files | phenology: stream the calendar | "
                        "events: stream one recording's events | "
                        "serve: answer OSC queries | map: print the address map")
    p.add_argument("input", nargs="?", default="./detected_events",
                   help="Output directory, events.json, or phenological_calendar.json")
    p.add_argument("--host", default="127.0.0.1", help="OSC target host")
    p.add_argument("--port", type=int, default=57120, help="OSC target port")
    p.add_argument("--listen-port", type=int, default=57121,
                   help="Port the query server listens on (serve mode)")
    p.add_argument("--days-per-second", type=float, default=1.0,
                   help="Phenology playback rate (default: 1 day per second)")
    p.add_argument("--loop", action="store_true",
                   help="Repeat the season until interrupted")


def _add_gallery_parser(sub) -> None:
    p = sub.add_parser(
        "gallery", help="rebuild the event-clip gallery",
        description="Rebuild gallery.html from existing events.json files.")
    p.add_argument("input", nargs="?", default="./detected_events",
                   help="Output directory containing events.json files")
    p.add_argument("-o", "--output", default="",
                   help="Gallery path (default: <input>/gallery.html)")
    p.add_argument("--title", default="Parliament of the Living",
                   help="Gallery heading")


def _add_media_parser(sub) -> None:
    p = sub.add_parser(
        "media", help="whole-file spectrogram, video split, video -> GIF",
        description="Utilities that used to be separate shell scripts.")
    p.add_argument("action", choices=("spectrogram", "poster", "split", "gif"),
                   help="spectrogram: whole-file video | poster: whole-file "
                        "PNG + thumbnail | split: size-limited parts | "
                        "gif: looping GIF")
    p.add_argument("files", nargs="+", help="Input files")
    p.add_argument("--size-limit", default="60M",
                   help="split: max size per part (default: 60M)")
    p.add_argument("--scale", default="scale=1080:-1",
                   help="split: ffmpeg scale filter")
    p.add_argument("--width", type=int, default=480, help="gif: output width")
    p.add_argument("--fps", type=int, default=12, help="gif: frame rate")
    p.add_argument("--max-freq", type=int, default=10000,
                   help="spectrogram: max frequency in Hz")
    p.add_argument("--color", default="cool", help="spectrogram: ffmpeg colormap")


def _add_metadata_parser(sub) -> None:
    p = sub.add_parser(
        "metadata", help="AudioMoth metadata report",
        description="Runs AudioMothRECS_LaLuna/audiomoth_processing.sh, which "
                    "extracts AudioMoth headers and builds the metadata report.")
    p.add_argument("input", help="Directory of AudioMoth recordings")


# --- config assembly --------------------------------------------------------

def config_from_detect_args(args: argparse.Namespace) -> Config:
    """Turn parsed `detect` arguments into a Config."""
    detector = DetectorConfig(
        baseline_window_s=args.baseline_window,
        pre_roll_s=args.pre_roll,
        post_roll_s=args.post_roll,
        max_clip_duration_s=args.max_clip_duration,
    )
    if args.sensitivity:
        apply_sensitivity(detector, args.sensitivity)
    # Explicit flags win over the preset
    if args.threshold is not None:
        detector.threshold_factor = args.threshold
    if args.min_event_duration is not None:
        detector.min_event_duration_s = args.min_event_duration
    if args.merge_gap is not None:
        detector.merge_gap_s = args.merge_gap

    config = Config(
        spectral=SpectralConfig(),
        detector=detector,
        clip=ClipConfig(
            organize_by=args.organize_by,
            make_video=not args.no_video,
            make_poster=not args.no_poster,
            make_gif=args.gif,
            make_reels=not args.no_reels,
            roles=args.roles,
            domains=args.domains,
            min_confidence=args.min_confidence,
        ),
        video=VideoConfig(
            max_freq=args.max_freq,
            style_by_domain=not args.no_style_by_domain,
        ),
        phenology=PhenologyConfig(write_csv=not args.no_csv),
        osc=OSCConfig(
            host=args.osc_host,
            port=args.osc_port,
            live=args.osc_live,
            days_per_second=args.days_per_second,
        ),
        output_dir=args.output_dir,
        no_video=args.no_video,
        json_only=args.json_only,
        no_osc=args.no_osc,
        build_phenology=args.phenology,
        build_gallery=not args.no_gallery,
    )
    if args.ultrasonic:
        # Explicit timing flags win over the mode's bat-scale defaults.
        apply_ultrasonic(config, adjust_timing=(args.merge_gap is None
                                                and args.min_event_duration is None))
    return config


# --- command handlers -------------------------------------------------------

def cmd_detect(args: argparse.Namespace) -> int:
    from .pipeline import run_batch

    unknown_roles = [r for r in args.roles if r not in ROLES]
    if unknown_roles:
        print(f"Unknown role(s): {', '.join(unknown_roles)}")
        print(f"Available: {', '.join(sorted(ROLES))}")
        return 2

    try:
        run_batch(args.inputs, config_from_detect_args(args))
    except FileNotFoundError as exc:
        print(exc)
        return 1
    return 0


def cmd_phenology(args: argparse.Namespace) -> int:
    from .pipeline import build_phenology, find_wav_files, run_batch

    source = Path(args.input)
    output_dir = args.output_dir or str(source)

    results = []
    if not args.reanalyze:
        try:
            results = store.load_results(str(source))
        except FileNotFoundError as exc:
            print(exc)
            return 1

    if results:
        print(f"Loaded {len(results)} existing result(s) from {source}")
        config = Config(
            phenology=PhenologyConfig(write_csv=not args.no_csv),
            osc=OSCConfig(days_per_second=args.days_per_second),
            output_dir=output_dir,
            no_osc=args.no_osc,
        )
        build_phenology(results, config)
        return 0

    if not find_wav_files(str(source)):
        print(f"No events.json files and no recordings found in {source}")
        print("Run `detect` first, or point this at a folder of WAV files.")
        return 1

    print(f"No existing results in {source} — analysing recordings "
          f"(metadata only, no clips).")
    config = Config(
        detector=DetectorConfig(threshold_factor=args.threshold),
        phenology=PhenologyConfig(write_csv=not args.no_csv),
        osc=OSCConfig(days_per_second=args.days_per_second),
        output_dir=args.output_dir or "./detected_events",
        json_only=True,
        no_osc=args.no_osc,
        build_phenology=True,
        build_gallery=False,
    )
    run_batch(str(source), config)
    return 0


def cmd_osc(args: argparse.Namespace) -> int:
    from .osc_output import (send_live_osc, stream_phenology,
                             write_osc_manifest, write_phenology_osc_file,
                             generate_phenology_supercollider_score)

    config = OSCConfig(
        host=args.host, port=args.port, listen_port=args.listen_port,
        days_per_second=args.days_per_second, loop=args.loop,
    )

    if args.mode == "map":
        target = Path(args.input)
        out = (target / "osc_address_map.txt" if target.is_dir()
               else Path("osc_address_map.txt"))
        write_osc_manifest(str(out), config)
        print(Path(out).read_text(encoding="utf-8"))
        print(f"(written to {out})")
        return 0

    if args.mode == "events":
        results = store.load_results(args.input)
        if not results:
            print(f"No events.json found under {args.input}")
            return 1
        for result in results:
            meta = {
                "filename": result.get("filename", ""),
                "habitat": result.get("habitat", ""),
                "season": result.get("season", ""),
                "datetime": result.get("datetime"),
                "temperature_c": result.get("temperature_c"),
                "democracy_index": result.get("parliament", {})
                                         .get("democracy_index", 0),
            }
            print(f"\n{result.get('filename')}")
            send_live_osc(result.get("events", []), meta, config)
        return 0

    calendar_path = _resolve_calendar(args.input)
    if not calendar_path:
        print(f"No phenological_calendar.json found at/under {args.input}")
        print("Build one with: ./bioacoustics.sh  ->  Phenological data")
        return 1

    if args.mode == "serve":
        from .osc_server import serve
        serve(calendar_path, config)
        return 0

    from .osc_server import load_calendar
    calendar = load_calendar(calendar_path)

    if args.mode == "phenology":
        stream_phenology(calendar, config)
        return 0

    # export
    out_dir = Path(calendar_path).parent
    osc_path = out_dir / "phenology.osc"
    scd_path = out_dir / "phenology_score.scd"
    map_path = out_dir / "osc_address_map.txt"
    write_phenology_osc_file(calendar, str(osc_path), config)
    generate_phenology_supercollider_score(calendar, str(scd_path), config)
    write_osc_manifest(str(map_path), config)
    print(f"Wrote {osc_path}")
    print(f"Wrote {scd_path}")
    print(f"Wrote {map_path}")
    return 0


def _resolve_calendar(target: str) -> str:
    path = Path(target)
    if path.is_file() and path.name.endswith(".json"):
        return str(path)
    if path.is_dir():
        return store.find_calendar(str(path))
    return ""


def cmd_gallery(args: argparse.Namespace) -> int:
    from .gallery import generate_gallery

    try:
        results = store.load_results(args.input)
    except FileNotFoundError as exc:
        print(exc)
        return 1
    if not results:
        print(f"No events.json found under {args.input}")
        return 1

    reels: dict[str, str] = {}
    for result in results:
        reels.update(result.get("reels", {}))

    output = args.output or str(Path(args.input) / "gallery.html")
    path = generate_gallery(results, output, reels=reels,
                            phenology_link=store.find_calendar(args.input)
                            .replace(".json", ".html"),
                            title=args.title)
    n_clips = sum(1 for r in results for e in r.get("events", [])
                  if e.get("clip_path") or e.get("video_path"))
    print(f"Wrote {path} ({n_clips} clips from {len(results)} recording(s))")
    return 0


def cmd_media(args: argparse.Namespace) -> int:
    from .media import have_ffmpeg, split_video, video_to_gif
    from .metadata import get_recording_metadata
    from .video import render_clip_poster, whole_file_video

    if not have_ffmpeg():
        print("ffmpeg not found on PATH. Install it first (brew install ffmpeg).")
        return 1

    for path in args.files:
        print(f"\n{Path(path).name}")
        try:
            if args.action == "spectrogram":
                config = VideoConfig(max_freq=args.max_freq, color=args.color,
                                     style_by_domain=False)
                meta = get_recording_metadata(path)
                dt = meta.get("datetime")
                out = whole_file_video(
                    path,
                    location_text=meta.get("habitat") or "AudioMoth Recording",
                    date_text=dt.strftime("%d %B %Y %H:%M") if dt else "",
                    config=config,
                )
                print(f"  Wrote {out}")
            elif args.action == "poster":
                config = VideoConfig(max_freq=args.max_freq,
                                     poster_color=args.color)
                stem = Path(path).with_suffix("")
                poster, thumb = render_clip_poster(
                    path, f"{stem}-fullsize.png", f"{stem}-thumbnail.png", config)
                for produced in (poster, thumb):
                    if produced:
                        print(f"  Wrote {produced}")
                if not poster:
                    print("  Failed: showspectrumpic produced nothing")
            elif args.action == "split":
                parts = split_video(path, args.size_limit, args.scale)
                print(f"  {len(parts)} part(s)")
            else:
                out = video_to_gif(path, width=args.width, fps=args.fps)
                print(f"  Wrote {out}")
        except Exception as exc:  # noqa: BLE001 - keep going through the batch
            print(f"  Failed: {exc}")
    return 0


def cmd_metadata(args: argparse.Namespace) -> int:
    script = REPO_ROOT / "AudioMothRECS_LaLuna" / "audiomoth_processing.sh"
    if not script.is_file():
        print(f"Missing {script}")
        return 1
    print(f"Running {script.name} on {args.input}")
    return subprocess.call(["bash", str(script), args.input],
                           cwd=str(script.parent))


def cmd_doctor(args: argparse.Namespace) -> int:
    from .media import (can_draw_text, ffmpeg_path, find_font, has_filter,
                        have_ffmpeg)
    from .video import check_renderer

    print("Bioacoustic toolkit — environment check")
    print("-" * 46)
    print(f"Python           {sys.version.split()[0]} ({sys.executable})")
    if sys.version_info < (3, 10):
        print("  ! Python 3.10+ is required.")

    for module in ("numpy", "scipy", "soundfile", "metamoth", "pythonosc"):
        try:
            __import__(module)
            print(f"{module:<16} ok")
        except ImportError:
            print(f"{module:<16} MISSING  (pip install -r requirements-detector.txt)")

    ok, detail = check_renderer()
    print(f"{'ffmpeg':<16} {'ok' if ok else 'MISSING'}  {detail}")
    if not have_ffmpeg():
        print("  ! Without ffmpeg you still get clips, JSON, OSC and phenology,")
        print("    but no spectrogram videos, posters or GIFs.")
        print("    macOS: brew install ffmpeg")
    else:
        print(f"{'  binary':<16} {ffmpeg_path()}")
        for name in ("showspectrum", "showspectrumpic", "drawtext",
                     "palettegen", "paletteuse"):
            state = "ok" if has_filter(name) else "missing"
            print(f"  {name:<14} {state}")
        if not can_draw_text():
            print("  ! No drawtext filter — this ffmpeg was built without")
            print("    libfreetype, so clip videos carry no burned-in label.")
            print("    Everything else renders. For labels:")
            print("      brew install ffmpeg-full   (picked up automatically)")
            print("    or point FFMPEG_BIN at a build that has drawtext.")
        elif not find_font():
            print("  Note: no bundled font found; drawtext will use "
                  "fontconfig's default.")

    script = REPO_ROOT / "AudioMothRECS_LaLuna" / "audiomoth_processing.sh"
    print(f"{'metadata tool':<16} {'ok' if script.is_file() else 'MISSING'}")
    print("-" * 46)
    print(f"Event types known: {len(ROLES)}")
    return 0


def cmd_wizard(args: argparse.Namespace) -> int:
    from .wizard import run

    return run()


HANDLERS = {
    "detect": cmd_detect,
    "phenology": cmd_phenology,
    "osc": cmd_osc,
    "gallery": cmd_gallery,
    "media": cmd_media,
    "metadata": cmd_metadata,
    "doctor": cmd_doctor,
    "wizard": cmd_wizard,
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Backward compatibility: `detect_events.sh recording.WAV --threshold 1.5`
    if argv and argv[0] not in SUBCOMMANDS and not argv[0].startswith("-"):
        argv.insert(0, "detect")

    parser = build_parser()
    if not argv:
        return cmd_wizard(argparse.Namespace())

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    try:
        return HANDLERS[args.command](args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
