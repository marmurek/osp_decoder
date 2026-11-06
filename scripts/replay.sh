#!/bin/sh
# Decodes an audio file (any format sox reads) once a receiver connects.
# Usage: scripts/replay.sh FILE [decoder options]
set -eu
file=$(realpath "$1")
shift
exec docker run --rm -p 8765:8765 -v "$file:/input/$(basename "$file"):ro" \
    -e OSP_INPUT_FILE="/input/$(basename "$file")" -e OSP_WAIT_FOR_RECEIVER=1 \
    osp-decoder:latest "$@"
