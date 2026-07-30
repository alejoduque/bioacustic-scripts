#!/bin/bash
# Superseded — kept as a working alias.
#
# This used to chain three scripts: a thumbnail per recording, a spectrogram
# movie per recording, then an HTML lightbox table of the pair. All three steps
# are now stages of one pipeline, and they operate on detected events instead of
# whole recordings:
#
#   ./bioacoustics.sh                     # guided, all features
#   ./detect_events.sh recordings/        # same pipeline, non-interactive
#
# What you get in place of the old three outputs:
#   • one WAV clip per detected event, filed under clips/<domain>/<role>/
#   • a spectrogram video per clip, colour-coded by acoustic domain
#   • a spectrogram still + thumbnail per clip
#   • one concatenated reel per event type
#   • gallery.html — the lightbox table, grouped by event type
#   • events.json / OSC exports / the phenological calendar
#
# Running this script now runs that pipeline on the files you pass it.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -eq 0 ]; then
    echo "No input files provided."
    echo "Usage: $0 /path/to/files/*.WAV"
    echo "   or: $0 /path/to/recordings/"
    echo ""
    echo "This now runs the unified pipeline: event clips + videos + stills +"
    echo "per-type reels + gallery + OSC. Run ./bioacoustics.sh for the guided"
    echo "version with every option explained."
    exit 1
fi

echo "Note: this is now './bioacoustics.sh detect'. Output is per-event rather"
echo "      than per-recording; see gallery.html when it finishes."
echo ""

exec "$SCRIPT_DIR/bioacoustics.sh" detect "$@" --phenology
