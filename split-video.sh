#!/bin/bash
# Superseded — kept as a working alias, with the original argument order.
#
# The splitting logic now lives in bioacoustic_detector/media.py:
#
#   ./bioacoustics.sh media split FILE... --size-limit 60M --scale scale=1080:-1
#
# Same approach as before (derive a video bitrate from the size budget, then
# re-encode fixed-length chunks), minus the dependency on `bc` and with audio
# re-encoded rather than copied, so each part is independently playable.
#
# Original approach by LukeLR.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -lt 2 ] || [ $# -gt 3 ]; then
    echo 'Illegal number of parameters. Needs 2-3 parameters:'
    echo 'Usage:'
    echo './split-video.sh FILE SIZELIMIT [SCALE]'
    echo
    echo 'Parameters:'
    echo '    - FILE:        Name of the video file to split'
    echo '    - SIZELIMIT:   Maximum file size of each part (e.g., 60M, 500M, 1G)'
    echo '    - SCALE:       Video scale filter (default: "scale=1080:-1")'
    echo
    echo 'Examples:'
    echo '    ./split-video.sh video.mp4 60M'
    echo '    ./split-video.sh video.mp4 500M "scale=720:-1"'
    echo
    echo 'Equivalent: ./bioacoustics.sh media split video.mp4 --size-limit 60M'
    exit 1
fi

FILE="$1"
SIZELIMIT="$2"
SCALE="${3:-scale=1080:-1}"

exec "$SCRIPT_DIR/bioacoustics.sh" media split "$FILE" \
    --size-limit "$SIZELIMIT" --scale "$SCALE"
