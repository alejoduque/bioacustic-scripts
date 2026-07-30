#!/bin/bash
# Bioacoustic Event Detector — direct access to the `detect` pipeline.
#
#   ./detect_events.sh recording.WAV
#   ./detect_events.sh recordings/ --phenology --sensitivity salient
#
# This is a thin front for `./bioacoustics.sh detect`, kept because it is the
# documented and scripted entry point. For the guided version of the same
# pipeline — and every other feature — run ./bioacoustics.sh with no arguments.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -eq 0 ]; then
    echo "Usage: $0 <WAV_FILE_OR_DIR> [options]"
    echo ""
    echo "Common options:"
    echo "  -o, --output-dir DIR     where to write results (./detected_events)"
    echo "      --sensitivity NAME   subtle | balanced | salient"
    echo "      --domains LIST       biophony,geophony,anthrophony,transition"
    echo "      --roles LIST         only clip these event types"
    echo "      --phenology          build the calendar and its OSC exports"
    echo "      --no-video           skip spectrogram rendering"
    echo "      --json-only          metadata only, no clips"
    echo ""
    echo "Full list:      $0 --help"
    echo "Guided version: ./bioacoustics.sh"
    exit 1
fi

exec "$SCRIPT_DIR/bioacoustics.sh" detect "$@"
