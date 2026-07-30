"""
Bidirectional OSC access to a phenological calendar.

Streaming (osc_output.stream_phenology) pushes a season at a fixed rate. An
installation often needs the opposite: to *ask* for a day when a visitor moves,
a sensor fires, or a sequencer wraps around. This server keeps a calendar in
memory and answers queries over UDP.

    /phenology/query/meta              -> header burst (extent, ranges, diel table)
    /phenology/query/day  <int>        -> that day's frame
    /phenology/query/date <str>        -> that date's frame (YYYY-MM-DD)
    /phenology/query/next              -> advance one day (wraps) and reply
    /phenology/query/prev              -> step back one day (wraps) and reply
    /phenology/query/events            -> every detected phenological shift
    /phenology/query/reply_port <int>  -> redirect replies to another port

Requires python-osc, which the launchers install into the managed venv.
"""

import json
import sys
from pathlib import Path

from .config import OSCConfig
from .osc_output import (build_phenology_event_messages,
                         build_phenology_frame_messages,
                         build_phenology_header_messages, send_messages)


def load_calendar(path: str) -> dict:
    """Load a phenological_calendar.json written by the detector."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "frames" not in data:
        raise ValueError(
            f"{path} has no 'frames' block — regenerate it with "
            "`./detect_events.sh <dir> --phenology`"
        )
    return data


class PhenologyOSCServer:
    """Serves a calendar over OSC. Replies are sent to a UDP client."""

    def __init__(self, calendar: dict, config: OSCConfig | None = None):
        from pythonosc.udp_client import SimpleUDPClient

        self.calendar = calendar
        self.config = config or OSCConfig()
        self.frames = calendar.get("frames", [])
        self.cursor = 0
        self._reply_port = self.config.port
        self._client = SimpleUDPClient(self.config.host, self._reply_port)
        self._by_date = {f.get("date"): i for i, f in enumerate(self.frames)}

    # --- replies ---

    def _reply(self, messages) -> None:
        send_messages(self._client, messages)

    def _send_frame(self, index: int) -> None:
        if not self.frames:
            return
        index = max(0, min(index, len(self.frames) - 1))
        self.cursor = index
        ns = self.config.phenology_namespace
        self._reply(build_phenology_frame_messages(self.frames[index], index, ns))
        print(f"  -> day {index} ({self.frames[index].get('date')})")

    # --- handlers ---

    def on_meta(self, address: str, *args) -> None:
        self._reply(build_phenology_header_messages(self.calendar, self.config))
        print("  -> meta")

    def on_day(self, address: str, *args) -> None:
        try:
            self._send_frame(int(args[0]))
        except (IndexError, TypeError, ValueError):
            print(f"  !! {address} needs an integer day index")

    def on_date(self, address: str, *args) -> None:
        date = str(args[0]) if args else ""
        index = self._by_date.get(date)
        if index is None:
            print(f"  !! no frame for date {date!r}")
            return
        self._send_frame(index)

    def on_next(self, address: str, *args) -> None:
        if self.frames:
            self._send_frame((self.cursor + 1) % len(self.frames))

    def on_prev(self, address: str, *args) -> None:
        if self.frames:
            self._send_frame((self.cursor - 1) % len(self.frames))

    def on_events(self, address: str, *args) -> None:
        ns = self.config.phenology_namespace
        for pheno_event in self.calendar.get("phenological_events", []):
            self._reply(build_phenology_event_messages(pheno_event, ns))
        print(f"  -> {len(self.calendar.get('phenological_events', []))} shifts")

    def on_reply_port(self, address: str, *args) -> None:
        from pythonosc.udp_client import SimpleUDPClient
        try:
            port = int(args[0])
        except (IndexError, TypeError, ValueError):
            print(f"  !! {address} needs an integer port")
            return
        self._reply_port = port
        self._client = SimpleUDPClient(self.config.host, port)
        print(f"  replies now go to {self.config.host}:{port}")

    # --- lifecycle ---

    def build_dispatcher(self):
        from pythonosc.dispatcher import Dispatcher

        ns = self.config.phenology_namespace.rstrip("/")
        dispatcher = Dispatcher()
        dispatcher.map(f"{ns}/query/meta", self.on_meta)
        dispatcher.map(f"{ns}/query/day", self.on_day)
        dispatcher.map(f"{ns}/query/date", self.on_date)
        dispatcher.map(f"{ns}/query/next", self.on_next)
        dispatcher.map(f"{ns}/query/prev", self.on_prev)
        dispatcher.map(f"{ns}/query/events", self.on_events)
        dispatcher.map(f"{ns}/query/reply_port", self.on_reply_port)
        dispatcher.set_default_handler(self._unhandled)
        return dispatcher

    def _unhandled(self, address: str, *args) -> None:
        print(f"  ?? unhandled {address} {list(args)}")

    def serve_forever(self) -> None:
        from pythonosc.osc_server import BlockingOSCUDPServer

        # Installations run this in the background with output to a log file;
        # block buffering would hide every query until the process exits.
        try:
            sys.stdout.reconfigure(line_buffering=True)
        except (AttributeError, OSError):
            pass

        server = BlockingOSCUDPServer(
            (self.config.listen_host, self.config.listen_port),
            self.build_dispatcher(),
        )
        ns = self.config.phenology_namespace.rstrip("/")
        print(f"Phenology OSC server listening on "
              f"{self.config.listen_host}:{self.config.listen_port}")
        print(f"  {len(self.frames)} day frames, "
              f"{len(self.calendar.get('phenological_events', []))} shifts loaded")
        print(f"  replies -> {self.config.host}:{self._reply_port}")
        print(f"  try: {ns}/query/meta, {ns}/query/next, {ns}/query/day 3")
        print("  Ctrl+C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
        finally:
            server.server_close()


def serve(calendar_path: str, config: OSCConfig | None = None) -> None:
    """Load a calendar from disk and serve it until interrupted."""
    PhenologyOSCServer(load_calendar(calendar_path), config).serve_forever()
