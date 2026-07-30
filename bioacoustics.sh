#!/bin/bash
# Bioacoustic toolkit — Parliament of the Living
#
# Single entry point. With no arguments it opens the guided wizard; with
# arguments it passes them straight to the CLI:
#
#   ./bioacoustics.sh                          # wizard
#   ./bioacoustics.sh detect recordings/ --phenology
#   ./bioacoustics.sh osc phenology detected_events/ --loop
#   ./bioacoustics.sh doctor
#
# Manages its own virtualenv, so there is nothing to install by hand.

set -uo pipefail

VENV_DIR="${BIOACOUSTIC_VENV:-$HOME/.bioacoustic_detector_venv}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQUIREMENTS="$SCRIPT_DIR/requirements-detector.txt"
STAMP="$VENV_DIR/.deps_installed"
MIN_PY="3.10"

# The package uses PEP 604 annotations (X | None), so 3.10 is a hard floor.
# macOS still ships 3.9 as /usr/bin/python3, and it is usually first on PATH,
# so search explicitly instead of trusting `python3`.
python_ok() {
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
        >/dev/null 2>&1
}

find_python() {
    local candidate
    for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 \
                     python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && python_ok "$candidate"; then
            command -v "$candidate"
            return 0
        fi
    done
    # Homebrew installs may not be on PATH in every shell
    for candidate in /opt/homebrew/bin/python3.1[0-9] /usr/local/bin/python3.1[0-9]; do
        if [ -x "$candidate" ] && python_ok "$candidate"; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

# Rebuild the venv if it is missing or predates the version floor
if [ -d "$VENV_DIR" ] && ! python_ok "$VENV_DIR/bin/python"; then
    echo "Existing virtualenv is older than Python $MIN_PY — rebuilding it."
    rm -rf "$VENV_DIR"
fi

if [ ! -d "$VENV_DIR" ]; then
    if ! PYTHON_CMD="$(find_python)"; then
        echo "Error: Python $MIN_PY or newer is required but was not found."
        echo "  macOS:  brew install python@3.12"
        echo "  Debian: sudo apt install python3.12 python3.12-venv"
        exit 1
    fi
    echo "Creating virtual environment with $PYTHON_CMD ($("$PYTHON_CMD" -V 2>&1))"
    "$PYTHON_CMD" -m venv "$VENV_DIR" || exit 1

    echo "Installing dependencies..."
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    "$VENV_DIR/bin/pip" install --quiet -r "$REQUIREMENTS" || exit 1
    touch "$STAMP"
    echo "Setup complete."
    echo ""
fi

# Reinstall only when requirements actually changed
if [ ! -f "$STAMP" ] || [ "$REQUIREMENTS" -nt "$STAMP" ]; then
    echo "Updating dependencies..."
    "$VENV_DIR/bin/pip" install --quiet -r "$REQUIREMENTS" && touch "$STAMP"
fi

# Only worth mentioning for the commands that actually render something
case "${1:-wizard}" in
    detect|media|wizard)
        if ! command -v ffmpeg >/dev/null 2>&1; then
            echo "Note: ffmpeg was not found on PATH."
            echo "      Detection, clips, OSC and phenology still work; spectrogram"
            echo "      video, stills and GIFs do not. macOS: brew install ffmpeg"
            echo ""
        fi
        ;;
esac

# Stay in the caller's directory so relative paths ("./recordings", "-o out")
# mean what the user typed, and make the package importable from anywhere.
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec "$VENV_DIR/bin/python" -m bioacoustic_detector.cli "$@"
