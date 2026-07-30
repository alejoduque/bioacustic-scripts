#!/bin/bash
# Superseded — kept as a working alias.
#
# Whole-recording spectrogram videos are now one option inside the toolkit
# rather than a script of their own, because a scrolling spectrogram of a whole
# hour buries the events worth looking at. The default path is:
#
#   ./bioacoustics.sh                       # guided
#   ./detect_events.sh recordings/          # one video per detected event
#
# This script still does what it always did, via:
#
#   ./bioacoustics.sh media spectrogram FILE...
#
# The render matches the old filter chain (996x592, cool, drange 72, scroll)
# and now also handles filenames containing commas, colons and accents, which
# the previous drawtext escaping did not.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -eq 0 ]; then
    echo "Usage: $0 recording1.WAV [recording2.WAV ...]"
    echo ""
    echo "Renders a spectrogram video for the complete duration of each file."
    echo "For one video per detected event instead, run: ./bioacoustics.sh"
    exit 1
fi

echo "Note: this is now './bioacoustics.sh media spectrogram'."
echo "      For event clips rather than whole files, run ./bioacoustics.sh"
echo ""

exec "$SCRIPT_DIR/bioacoustics.sh" media spectrogram "$@"
