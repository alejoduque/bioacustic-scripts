#!/bin/bash
# Superseded — kept as a working alias.
#
# The GIF conversion now lives in bioacoustic_detector/media.py:
#
#   ./bioacoustics.sh media gif FILE... [--width 480] [--fps 12]
#
# Why it moved: this script hard-coded /opt/homebrew paths for mplayer,
# ImageMagick and gifsicle, extracted every frame to PNG on disk, then optimized
# the result in two more passes. The replacement uses ffmpeg's
# palettegen/paletteuse, which needs no extra tools, touches no temp frames, and
# keeps the same behaviour: shrink the long edge to 480px, optimize the palette,
# loop forever.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -eq 0 ]; then
    echo "Usage: $0 video_file [video_file2 ...]"
    echo ""
    echo "Now: ./bioacoustics.sh media gif FILE... [--width N] [--fps N]"
    exit 1
fi

echo "Note: this is now './bioacoustics.sh media gif' (ffmpeg only — no"
echo "      mplayer, ImageMagick or gifsicle needed)."
echo ""

exec "$SCRIPT_DIR/bioacoustics.sh" media gif "$@"
