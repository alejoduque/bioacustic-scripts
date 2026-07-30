"""
Interactive wizard: one guided front-end for every feature in the toolkit.

Each flow explains what it does, asks only for what it cannot infer, states
what it is about to do, and finishes by pointing at the files it produced and
the next thing you would plausibly want to run.

Answers persist in ~/.bioacoustics_wizard.json so the second run is mostly
pressing Enter.
"""

import json
import subprocess
import sys
from pathlib import Path

from . import store
from .classifier import ROLES
from .config import (SENSITIVITY_PRESETS, ClipConfig, Config, DetectorConfig,
                     OSCConfig, PhenologyConfig, VideoConfig,
                     apply_sensitivity, apply_ultrasonic)

STATE_PATH = Path.home() / ".bioacoustics_wizard.json"
REPO_ROOT = Path(__file__).resolve().parent.parent

_COLOR = sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def bold(text: str) -> str:
    return _c(text, "1")


def dim(text: str) -> str:
    return _c(text, "2")


def accent(text: str) -> str:
    return _c(text, "36")


def warn(text: str) -> str:
    return _c(text, "33")


# --- state ------------------------------------------------------------------

def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass  # a read-only home is not worth failing a run over


# --- prompts ----------------------------------------------------------------

class Abort(Exception):
    """Raised to return to the main menu."""


def _read(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        raise Abort() from None


def ask(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = _read(f"{accent('?')} {question}{dim(suffix)}: ")
    if answer.lower() in ("q", "quit", "back") and default.lower() != answer.lower():
        raise Abort()
    return answer or default


def ask_path(question: str, default: str = "", must_exist: bool = True) -> str:
    while True:
        raw = ask(question, default)
        if not raw:
            print(warn("  A path is required."))
            continue
        path = Path(raw).expanduser()
        if must_exist and not path.exists():
            print(warn(f"  Not found: {path}"))
            continue
        return str(path)


def ask_bool(question: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        answer = ask(f"{question} ({hint})", "").lower()
        if not answer:
            return default
        if answer in ("y", "yes", "s", "si", "sí"):
            return True
        if answer in ("n", "no"):
            return False
        print(warn("  Please answer y or n."))


def ask_number(question: str, default: float, cast=float,
               low: float | None = None, high: float | None = None):
    while True:
        raw = ask(question, str(default))
        try:
            value = cast(raw)
        except ValueError:
            print(warn(f"  Expected a number, got {raw!r}."))
            continue
        if low is not None and value < low:
            print(warn(f"  Must be at least {low}."))
            continue
        if high is not None and value > high:
            print(warn(f"  Must be at most {high}."))
            continue
        return value


def ask_choice(question: str, options: list[tuple[str, str]],
               default: str = "") -> str:
    """options: list of (value, description). Returns the chosen value."""
    print(f"\n{accent('?')} {bold(question)}")
    for i, (value, description) in enumerate(options, 1):
        marker = accent("*") if value == default else " "
        print(f"  {marker} {bold(str(i))}. {value}{dim(' — ' + description) if description else ''}")
    values = [v for v, _ in options]
    while True:
        raw = ask("Choice", default or values[0])
        if raw in values:
            return raw
        if raw.isdigit() and 1 <= int(raw) <= len(values):
            return values[int(raw) - 1]
        print(warn(f"  Pick 1-{len(values)} or a name."))


def ask_multi(question: str, options: list[str],
              default_all: bool = True) -> tuple:
    """Pick several options. Empty answer = all of them."""
    print(f"\n{accent('?')} {bold(question)}")
    for i, option in enumerate(options, 1):
        print(f"    {bold(str(i))}. {option}")
    print(dim("    Enter numbers or names separated by commas; blank = all."))
    raw = ask("Selection", "")
    if not raw:
        return () if default_all else tuple(options)

    chosen = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if token.isdigit() and 1 <= int(token) <= len(options):
            chosen.append(options[int(token) - 1])
        elif token in options:
            chosen.append(token)
        else:
            print(warn(f"  Ignoring unknown option {token!r}"))
    return tuple(chosen)


def section(title: str, blurb: str = "") -> None:
    print()
    print(bold("─" * 64))
    print(bold(f" {title}"))
    if blurb:
        for line in blurb.strip().splitlines():
            print(dim(f" {line.strip()}"))
    print(bold("─" * 64))


def confirm_and_run(summary: list[tuple[str, str]], action) -> bool:
    """Show a plan, ask once, then run it."""
    print(f"\n{bold('Plan')}")
    width = max(len(label) for label, _ in summary)
    for label, value in summary:
        print(f"  {label.rjust(width)} : {value}")
    if not ask_bool("\nRun this?", True):
        print(dim("Cancelled."))
        return False
    print()
    action()
    return True


# --- feature flows ----------------------------------------------------------

def flow_detect(state: dict) -> None:
    section(
        "Detect events and cut video clips",
        """Scans recordings for spectral shifts — a species starting up, rain
        arriving, the dawn chorus turning over — and cuts one clip per event
        with its own spectrogram video, colour-coded by acoustic domain.
        This is also the step that produces the data everything else reads.""")

    source = ask_path("Recording file or folder", state.get("input", ""))
    output = ask("Output folder", state.get("output", "./detected_events"))

    preset = ask_choice(
        "Detection sensitivity",
        [(name, spec["description"]) for name, spec in SENSITIVITY_PRESETS.items()],
        state.get("sensitivity", "balanced"))

    print(f"\n{dim('Clips carry context on both sides of the event.')}")
    pre_roll = ask_number("Seconds before onset", state.get("pre_roll", 20.0))
    post_roll = ask_number("Seconds after offset", state.get("post_roll", 10.0))

    domains = ask_multi("Which acoustic domains do you want clips for?",
                        ["biophony", "geophony", "anthrophony", "transition"])

    roles: tuple = ()
    if ask_bool("Narrow it down to specific event types?", False):
        candidates = sorted(ROLES) if not domains else sorted(
            r for r, d in ROLES.items() if d in domains)
        roles = ask_multi("Event types", candidates)

    print()
    make_video = ask_bool("Render a spectrogram video per clip?", True)
    make_poster = ask_bool("Render a spectrogram still + thumbnail per clip?", True)
    make_gif = ask_bool("Also render a looping GIF per clip?", False)
    make_reels = make_video and ask_bool(
        "Concatenate all clips of the same type into one reel per type?", True)

    build_phenology = ask_bool(
        "Build the phenological calendar and its OSC exports afterwards?", True)
    days_per_second = 1.0
    if build_phenology:
        days_per_second = ask_number(
            "OSC playback rate (days per second)", state.get("dps", 1.0))

    detector = DetectorConfig(pre_roll_s=pre_roll, post_roll_s=post_roll)
    apply_sensitivity(detector, preset)

    config = Config(
        detector=detector,
        clip=ClipConfig(make_video=make_video, make_poster=make_poster,
                        make_gif=make_gif, make_reels=make_reels,
                        roles=roles, domains=domains),
        video=VideoConfig(),
        phenology=PhenologyConfig(),
        osc=OSCConfig(days_per_second=days_per_second),
        output_dir=output,
        no_video=not make_video,
        build_phenology=build_phenology,
    )

    state.update({"input": source, "output": output, "sensitivity": preset,
                  "pre_roll": pre_roll, "post_roll": post_roll,
                  "dps": days_per_second})

    from .pipeline import find_wav_files, run_batch
    wav_files = find_wav_files(source)
    if not wav_files:
        print(warn(f"No WAV files found in {source}"))
        return

    # Only raise ultrasound when the recordings can actually contain it.
    if _max_sample_rate(wav_files) > 96000:
        print(warn("\n  These recordings were made above 96 kHz, so they may "
                   "carry bat echolocation."))
        print(dim("  Normal analysis downsamples to 48 kHz and discards "
                  "everything above 24 kHz."))
        if ask_bool("Analyse at the native rate to keep ultrasound?", True):
            apply_ultrasonic(config)

    _warn_if_no_ffmpeg(make_video or make_poster or make_gif)

    summary = [
        ("recordings", f"{len(wav_files)} file(s)"),
        ("output", output),
        ("sensitivity", f"{preset} (threshold {detector.threshold_factor} MAD)"),
        ("clip padding", f"-{pre_roll:g}s / +{post_roll:g}s"),
        ("domains", ", ".join(domains) if domains else "all"),
        ("event types", ", ".join(roles) if roles else "all"),
        ("media", ", ".join(filter(None, [
            "video" if make_video else "", "still" if make_poster else "",
            "gif" if make_gif else "", "reels" if make_reels else ""])) or "none"),
        ("analysis band", "native rate, incl. ultrasound" if config.ultrasonic
         else "0-24 kHz (48 kHz analysis)"),
        ("phenology", "yes" if build_phenology else "no"),
    ]

    outcome: dict = {}

    def action() -> None:
        outcome.update(run_batch(source, config))

    if not confirm_and_run(summary, action):
        return

    print(f"\n{bold('Next steps')}")
    if outcome.get("gallery"):
        print(f"  {'Browse clips':<18} open {outcome['gallery']}")
    if outcome.get("phenology", {}).get("html"):
        print(f"  {'Read the calendar':<18} open {outcome['phenology']['html']}")
    if build_phenology:
        print(f"  {'Stream over OSC':<18} menu option 3 -> stream the calendar")


def flow_phenology(state: dict) -> None:
    section(
        "Phenological calendar",
        """Turns a folder of processed recordings into dated ecological series:
        daily activity, role richness, biophony/geophony balance, dawn chorus
        drift, and the shifts between them. Every value is also normalized to
        0-1 so it can drive a control voltage. Written as JSON, CSV, HTML and
        two OSC formats.""")

    source = ask_path("Folder with detection output (or recordings)",
                      state.get("output", "./detected_events"))

    results = []
    try:
        results = store.load_results(source)
    except FileNotFoundError:
        pass

    if results:
        dated = sum(1 for r in results if r.get("datetime"))
        print(f"\n  Found {len(results)} processed recording(s); "
              f"{dated} carry a timestamp.")
        if dated < 2:
            print(warn("  A calendar needs recordings from at least two days."))
    else:
        print(dim("\n  No events.json here — recordings will be analysed first "
                  "(metadata only, no clips)."))

    days_per_second = ask_number("OSC playback rate (days per second)",
                                 state.get("dps", 1.0))
    write_csv = ask_bool("Write the tidy CSV as well?", True)
    state.update({"dps": days_per_second})

    from .pipeline import build_phenology, find_wav_files, run_batch

    config = Config(
        phenology=PhenologyConfig(write_csv=write_csv),
        osc=OSCConfig(days_per_second=days_per_second),
        output_dir=source,
        json_only=not results,
        build_phenology=True,
        build_gallery=False,
    )

    def action() -> None:
        if results:
            build_phenology(results, config)
        else:
            run_batch(source, config)

    summary = [
        ("source", source),
        ("mode", "reuse existing results" if results else "analyse recordings"),
        ("playback", f"{days_per_second:g} day(s) per second"),
        ("csv", "yes" if write_csv else "no"),
    ]
    if not results and not find_wav_files(source):
        print(warn(f"Nothing to work with in {source}"))
        return
    if not confirm_and_run(summary, action):
        return

    print(f"\n{bold('Next steps')}")
    print(f"  Inspect     open {Path(source) / 'phenological_calendar.html'}")
    print("  Stream OSC  menu option 3 -> stream the calendar")


def flow_osc(state: dict) -> None:
    section(
        "OSC",
        """Send the ecology out to instruments. The calendar is the main
        payload: a season becomes a timed control stream, every scalar sent as
        [raw value, 0-1 normalized] so a patch can take either.""")

    mode = ask_choice("What do you want to do?", [
        ("stream-phenology", "replay the calendar to a host:port, in compressed time"),
        ("serve", "listen for OSC queries and answer with calendar data"),
        ("export", "write phenology.osc + SuperCollider score + address map"),
        ("stream-events", "replay one recording's events at their real onsets"),
        ("map", "print the OSC address map"),
    ], state.get("osc_mode", "stream-phenology"))
    state["osc_mode"] = mode

    source = ask_path("Detection output folder",
                      state.get("output", "./detected_events"))

    host = ask("OSC target host", state.get("osc_host", "127.0.0.1"))
    port = ask_number("OSC target port", state.get("osc_port", 57120), int)
    state.update({"osc_host": host, "osc_port": port})

    config = OSCConfig(host=host, port=port)

    if mode == "map":
        from .osc_output import write_osc_manifest
        out = Path(source) / "osc_address_map.txt"
        write_osc_manifest(str(out), config)
        print()
        print(out.read_text(encoding="utf-8"))
        return

    if mode == "stream-events":
        results = store.load_results(source)
        if not results:
            print(warn(f"No events.json under {source}"))
            return
        options = [(r.get("filename", "?"), f"{r.get('n_events', 0)} events")
                   for r in results]
        chosen = ask_choice("Which recording?", options, options[0][0])
        result = next(r for r in results if r.get("filename") == chosen)

        from .osc_output import send_live_osc
        meta = {
            "filename": result.get("filename", ""),
            "habitat": result.get("habitat", ""),
            "season": result.get("season", ""),
            "datetime": result.get("datetime"),
            "temperature_c": result.get("temperature_c"),
            "democracy_index": result.get("parliament", {}).get("democracy_index", 0),
        }
        summary = [("recording", chosen),
                   ("events", str(result.get("n_events", 0))),
                   ("target", f"{host}:{port}")]
        confirm_and_run(summary,
                        lambda: send_live_osc(result.get("events", []), meta, config))
        return

    calendar_path = store.find_calendar(source)
    if not calendar_path:
        print(warn(f"No phenological_calendar.json under {source}."))
        print(dim("  Build one first with menu option 2."))
        return

    from .osc_server import load_calendar
    calendar = load_calendar(calendar_path)
    n_days = len(calendar.get("frames", []))
    print(f"\n  Calendar: {n_days} day(s), "
          f"{len(calendar.get('phenological_events', []))} shift(s)")

    if mode == "serve":
        listen_port = ask_number("Port to listen on",
                                 state.get("listen_port", 57121), int)
        state["listen_port"] = listen_port
        config = OSCConfig(host=host, port=port, listen_port=listen_port)

        from .osc_server import PhenologyOSCServer
        summary = [("calendar", calendar_path),
                   ("listening", f"0.0.0.0:{listen_port}"),
                   ("replies to", f"{host}:{port}")]
        confirm_and_run(
            summary, lambda: PhenologyOSCServer(calendar, config).serve_forever())
        return

    if mode == "export":
        from .osc_output import (generate_phenology_supercollider_score,
                                write_osc_manifest, write_phenology_osc_file)
        rate = ask_number("Playback rate baked into the export (days per second)",
                          state.get("dps", 1.0))
        config = OSCConfig(host=host, port=port, days_per_second=rate)
        out_dir = Path(calendar_path).parent

        def action() -> None:
            print(f"Wrote {write_phenology_osc_file(calendar, str(out_dir / 'phenology.osc'), config)}")
            print(f"Wrote {generate_phenology_supercollider_score(calendar, str(out_dir / 'phenology_score.scd'), config)}")
            print(f"Wrote {write_osc_manifest(str(out_dir / 'osc_address_map.txt'), config)}")

        confirm_and_run([("calendar", calendar_path),
                         ("rate", f"{rate:g} day(s)/s"),
                         ("into", str(out_dir))], action)
        return

    # stream-phenology
    rate = ask_number("Days per second", state.get("dps", 1.0), low=0.001)
    loop = ask_bool("Loop the season until interrupted?", False)
    state["dps"] = rate
    config = OSCConfig(host=host, port=port, days_per_second=rate, loop=loop)

    from .osc_output import stream_phenology
    summary = [("calendar", calendar_path),
               ("days", str(n_days)),
               ("target", f"{host}:{port}"),
               ("rate", f"{rate:g} day(s)/s -> {n_days / rate:.1f}s per pass"),
               ("loop", "yes" if loop else "no")]
    confirm_and_run(summary, lambda: stream_phenology(calendar, config))


def flow_gallery(state: dict) -> None:
    section(
        "Event clip gallery",
        """Rebuilds gallery.html from results already on disk: one card per
        event clip, grouped by ecological role, with a lightbox player and
        per-type reels. Cheap to re-run after re-rendering media.""")

    source = ask_path("Detection output folder",
                      state.get("output", "./detected_events"))
    try:
        results = store.load_results(source)
    except FileNotFoundError as exc:
        print(warn(str(exc)))
        return
    if not results:
        print(warn(f"No events.json under {source}. Run option 1 first."))
        return

    n_clips = sum(1 for r in results for e in r.get("events", [])
                  if e.get("clip_path") or e.get("video_path"))
    if not n_clips:
        print(warn("Those results have no clips — nothing to show in a gallery."))
        print(dim("  Re-run detection without --json-only to cut clips."))
        return

    title = ask("Gallery heading", state.get("gallery_title",
                                             "Parliament of the Living"))
    state["gallery_title"] = title

    from .gallery import generate_gallery
    reels: dict[str, str] = {}
    for result in results:
        reels.update(result.get("reels", {}))
    output = str(Path(source) / "gallery.html")
    pheno = store.find_calendar(source).replace(".json", ".html")

    def action() -> None:
        path = generate_gallery(results, output, reels=reels,
                                phenology_link=pheno, title=title)
        print(f"Wrote {path}")

    confirm_and_run([("recordings", str(len(results))),
                     ("clips", str(n_clips)),
                     ("reels", str(len(reels))),
                     ("output", output)], action)


def flow_metadata(state: dict) -> None:
    section(
        "AudioMoth metadata report",
        """Reads AudioMoth headers (timestamp, temperature, battery, gain,
        sample rate) and builds the interactive metadata report with habitat
        and season parsed from the folder names.""")

    script = REPO_ROOT / "AudioMothRECS_LaLuna" / "audiomoth_processing.sh"
    if not script.is_file():
        print(warn(f"Missing {script}"))
        return

    source = ask_path("Folder of AudioMoth recordings", state.get("input", ""))
    state["input"] = source

    confirm_and_run(
        [("script", script.name), ("folder", source)],
        lambda: subprocess.call(["bash", str(script), source],
                                cwd=str(script.parent)))


def flow_media(state: dict) -> None:
    section(
        "Media utilities",
        """The general-purpose video tools, plus the whole-recording
        spectrogram for when you deliberately want the full hour instead of
        event clips.""")

    action_name = ask_choice("Which utility?", [
        ("spectrogram", "whole-recording spectrogram video (no event detection)"),
        ("poster", "whole-recording spectrogram PNG + thumbnail"),
        ("gif", "video -> optimized looping GIF"),
        ("split", "split a video into size-limited parts"),
    ], "spectrogram")

    from .media import have_ffmpeg
    if not have_ffmpeg():
        print(warn("ffmpeg is not installed — these tools all need it."))
        print(dim("  macOS: brew install ffmpeg"))
        return

    target = ask_path("File or folder", state.get("media_input", ""))
    state["media_input"] = target

    path = Path(target)
    if action_name in ("spectrogram", "poster"):
        files = ([str(path)] if path.is_file()
                 else [str(f) for f in sorted(path.rglob("*"))
                       if f.suffix.lower() == ".wav"])
    else:
        exts = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}
        files = ([str(path)] if path.is_file()
                 else [str(f) for f in sorted(path.rglob("*"))
                       if f.suffix.lower() in exts])

    if not files:
        print(warn(f"No matching files under {target}"))
        return

    from .media import split_video, video_to_gif
    from .metadata import get_recording_metadata
    from .video import render_clip_poster, whole_file_video

    if action_name == "poster":
        max_freq = ask_number("Top frequency to show (Hz)", 10000, int)
        color = ask_choice("Colormap", [
            ("fruit", "high contrast, the original thumbnail look"),
            ("cool", "blue/teal"),
            ("viridis", "perceptually uniform"),
        ], "fruit")
        config = VideoConfig(max_freq=max_freq, poster_color=color)

        def action() -> None:
            for f in files:
                stem = Path(f).with_suffix("")
                poster, thumb = render_clip_poster(
                    f, f"{stem}-fullsize.png", f"{stem}-thumbnail.png", config)
                if poster:
                    print(f"  Wrote {poster}"
                          + (f" and {Path(thumb).name}" if thumb else ""))
                else:
                    print(warn(f"  {Path(f).name}: render failed"))

        confirm_and_run([("files", str(len(files))),
                         ("top frequency", f"{max_freq} Hz"),
                         ("colormap", color)], action)
        return

    if action_name == "spectrogram":
        max_freq = ask_number("Top frequency to show (Hz)", 10000, int)
        color = ask_choice("Colormap", [
            ("cool", "blue/teal, the project default"),
            ("fruit", "high contrast, good for stills"),
            ("fiery", "warm"),
            ("viridis", "perceptually uniform"),
        ], "cool")
        config = VideoConfig(max_freq=max_freq, color=color,
                            style_by_domain=False)

        def action() -> None:
            for f in files:
                meta = get_recording_metadata(f)
                dt = meta.get("datetime")
                try:
                    out = whole_file_video(
                        f, location_text=meta.get("habitat") or "AudioMoth Recording",
                        date_text=dt.strftime("%d %B %Y %H:%M") if dt else "",
                        config=config)
                    print(f"  Wrote {out}")
                except Exception as exc:  # noqa: BLE001
                    print(warn(f"  {Path(f).name}: {exc}"))

        confirm_and_run([("files", str(len(files))),
                         ("top frequency", f"{max_freq} Hz"),
                         ("colormap", color)], action)
        return

    if action_name == "gif":
        width = ask_number("Output width in pixels", 480, int)
        fps = ask_number("Frame rate", 12, int)

        def action() -> None:
            for f in files:
                try:
                    print(f"  Wrote {video_to_gif(f, width=width, fps=fps)}")
                except Exception as exc:  # noqa: BLE001
                    print(warn(f"  {Path(f).name}: {exc}"))

        confirm_and_run([("files", str(len(files))),
                         ("width", f"{width}px"), ("fps", str(fps))], action)
        return

    size_limit = ask("Maximum size per part (e.g. 60M, 1G)", "60M")
    scale = ask("Scale filter", "scale=1080:-1")

    def action() -> None:
        for f in files:
            print(f"  {Path(f).name}")
            try:
                parts = split_video(f, size_limit, scale)
                print(f"  {len(parts)} part(s)")
            except Exception as exc:  # noqa: BLE001
                print(warn(f"  {Path(f).name}: {exc}"))

    confirm_and_run([("files", str(len(files))),
                     ("size limit", size_limit), ("scale", scale)], action)


def flow_hdr(state: dict) -> None:
    section(
        "HDR photo batch (DJI DNG)",
        """Fuses bracketed DNG sets into HDR JPEGs with dcraw + enfuse. Kept
        alongside the audio tools because it processes the same field surveys.""")

    script = REPO_ROOT / "HDR-DNG-DJI-IMGS"
    if not script.is_file():
        print(warn(f"Missing {script}"))
        return

    folder = ask_path("Folder containing the .DNG files",
                      state.get("hdr_input", ""))
    state["hdr_input"] = folder

    n_dng = len([f for f in Path(folder).glob("*.DNG")])
    if not n_dng:
        print(warn(f"No .DNG files in {folder}"))
        return
    print(dim(f"  {n_dng} DNG file(s); the script fuses them in sets of 5 "
              f"and will ask for an output base name."))

    confirm_and_run(
        [("script", script.name), ("folder", folder), ("dng files", str(n_dng))],
        lambda: subprocess.call(["bash", str(script)], cwd=folder))


def flow_doctor(state: dict) -> None:
    section("Environment check", "What is installed, and what that enables.")
    from .cli import cmd_doctor
    import argparse
    cmd_doctor(argparse.Namespace())


def _max_sample_rate(wav_files: list[str]) -> int:
    """Highest sample rate across a set of recordings (0 if unreadable)."""
    import soundfile as sf

    best = 0
    for path in wav_files[:50]:  # a sample is enough to spot an ultrasonic deployment
        try:
            best = max(best, sf.info(path).samplerate)
        except Exception:  # noqa: BLE001 - a bad file should not stop the flow
            continue
    return best


def _warn_if_no_ffmpeg(wants_media: bool) -> None:
    if not wants_media:
        return
    from .media import have_ffmpeg
    if not have_ffmpeg():
        print(warn("\n  ffmpeg is not installed, so no video/still/GIF will be "
                   "produced."))
        print(dim("  Clips, JSON, OSC and the calendar are unaffected. "
                  "macOS: brew install ffmpeg"))


# --- menu -------------------------------------------------------------------

MENU = [
    ("1", "Detect events and cut video clips", flow_detect,
     "the core pipeline — start here"),
    ("2", "Phenological calendar", flow_phenology,
     "dated ecological series + OSC exports"),
    ("3", "OSC", flow_osc,
     "stream, serve or export for instruments"),
    ("4", "Event clip gallery", flow_gallery,
     "browse the clips by event type"),
    ("5", "AudioMoth metadata report", flow_metadata,
     "headers, temperature, battery"),
    ("6", "Media utilities", flow_media,
     "whole-file spectrogram, GIF, split"),
    ("7", "HDR photo batch (DJI DNG)", flow_hdr,
     "bracketed stills from the same surveys"),
    ("8", "Environment check", flow_doctor,
     "what is installed"),
]


def print_menu() -> None:
    print()
    print(bold("  Bioacoustic toolkit — Parliament of the Living"))
    print(dim("  AudioMoth recordings -> event clips -> phenological data -> OSC"))
    print()
    for key, title, _, blurb in MENU:
        print(f"   {bold(key)}  {title}")
        print(f"      {dim(blurb)}")
    print(f"   {bold('q')}  Quit")
    print(dim("\n  Inside a flow, 'q' returns here."))


def run() -> int:
    state = load_state()
    handlers = {key: flow for key, _, flow, _ in MENU}

    while True:
        print_menu()
        try:
            choice = input(f"\n{accent('>')} Choose: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice in ("q", "quit", "exit"):
            break
        flow = handlers.get(choice)
        if not flow:
            print(warn(f"  Unknown option {choice!r}"))
            continue

        try:
            flow(state)
        except Abort:
            print(dim("\n  Back to the menu."))
        except KeyboardInterrupt:
            print(dim("\n  Interrupted — back to the menu."))
        except Exception as exc:  # noqa: BLE001 - never drop the user out
            print(warn(f"\n  That flow failed: {exc}"))
        finally:
            save_state(state)

    save_state(state)
    print(dim("Bye."))
    return 0
