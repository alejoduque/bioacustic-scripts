#!/bin/bash
# Superseded — kept as a working alias.
#
# This was a byte-identical copy of enhanced_html_generator.sh (same md5); both
# now point at the single gallery implementation in
# bioacoustic_detector/gallery.py. See enhanced_html_generator.sh for the full
# note on what changed and what carried over.
#
#   ./bioacoustics.sh gallery [OUTPUT_DIR]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Note: this is now './bioacoustics.sh gallery'. It reads events.json"
echo "      files and writes gallery.html (not index.html)."
echo ""

exec "$SCRIPT_DIR/bioacoustics.sh" gallery "$@"
