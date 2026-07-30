#!/bin/bash
# Superseded — kept as a working alias.
#
# This file and make-html-lightbox-table-fixed.sh were byte-identical copies of
# the same 820-line generator. Both are now aliases for one implementation,
# bioacoustic_detector/gallery.py:
#
#   ./bioacoustics.sh gallery [OUTPUT_DIR]
#
# What changed:
#   • one card per detected event, grouped by ecological role, instead of one
#     row per recording
#   • reads events.json instead of scanning the working directory for
#     *-thumbnail.png, so it no longer depends on ffprobe + jq + numfmt
#   • self-contained lightbox (no perfundo.min.css, no spectrogram-table.css)
#   • writes gallery.html in the output directory rather than overwriting
#     ./index.html
#
# Carried over unchanged: search, the lightbox, and per-recording GPS entry —
# still stored in localStorage under 'audiomoth-gps' and keyed by recording
# name, so coordinates you saved with the old gallery still load.
#
# Prerequisite: run detection first, so there is something to show.
#   ./detect_events.sh recordings/

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Note: this is now './bioacoustics.sh gallery'. It reads events.json"
echo "      files and writes gallery.html (not index.html)."
echo ""

exec "$SCRIPT_DIR/bioacoustics.sh" gallery "$@"
