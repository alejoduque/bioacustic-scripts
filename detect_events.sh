#!/bin/bash
# Bioacoustic Event Detector — Parliament of the Living
# Bash wrapper: sets up venv and delegates to Python CLI

VENV_DIR="$HOME/.bioacoustic_detector_venv"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQUIREMENTS="$SCRIPT_DIR/requirements-detector.txt"

# Detect Python
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "Error: Python is not installed"
    exit 1
fi

# Create venv if needed
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv "$VENV_DIR"

    echo "Installing dependencies..."
    "$VENV_DIR/bin/pip" install --quiet -r "$REQUIREMENTS"

    echo "Setup complete."
    echo ""
fi

# Check if dependencies need updating
if [ "$REQUIREMENTS" -nt "$VENV_DIR/.deps_installed" ]; then
    echo "Updating dependencies..."
    "$VENV_DIR/bin/pip" install --quiet -r "$REQUIREMENTS"
    touch "$VENV_DIR/.deps_installed"
fi

# Run the detector
cd "$SCRIPT_DIR"
exec "$VENV_DIR/bin/python" -m bioacoustic_detector.cli "$@"
