#!/bin/sh
# Prints events of a running decoder; stop with Ctrl+C.
# Usage: scripts/monitor.sh [ws://host:8765/] [--raw]
set -eu
exec docker run --rm -it --network host --no-healthcheck \
    --entrypoint python3 osp-decoder:latest -m osp_decoder.monitor "$@"
