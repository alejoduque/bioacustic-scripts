#!/bin/bash
# Superseded — kept as a working alias.
#
# Original: Copyright (c) 2020, lowkey digital studio / Nathan Wolek (MIT),
# modified for the YYYYMMDD_HHMMSS.WAV format. The showspectrumpic recipe it
# established lives on in bioacoustic_detector/video.py, where it now runs per
# detected event clip so every voice in the parliament gets its own cover image
# instead of one image per hour of tape.
#
# Whole-file stills are still available:
#
#   ./bioacoustics.sh media poster FILE...
#
# Outputs, as before: <name>-fullsize.png and <name>-thumbnail.png
# (the thumbnail is now 256x144 rather than 128x72).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -eq 0 ]; then
    echo "Usage: $0 recording1.WAV [recording2.WAV ...]"
    echo ""
    echo "Renders a spectrogram PNG + thumbnail for each complete file."
    echo "For per-event spectrograms instead, run: ./bioacoustics.sh"
    exit 1
fi

echo "Note: this is now './bioacoustics.sh media poster'."
echo "      For per-event spectrograms, run ./bioacoustics.sh"
echo ""

exec "$SCRIPT_DIR/bioacoustics.sh" media poster --color fruit "$@"
