#!/bin/sh
# Decodes the audio played on this PC (e.g. a video in the browser) by
# capturing the PipeWire output monitor. Stop with Ctrl+C.
# Extra arguments are passed to the decoder, e.g. --protocols STQC,DTMF.
set -eu
pw-record -P stream.capture.sink=true --rate 22050 --channels 1 --format s16 --raw - \
    | docker run --rm -i --name osp-desktop-audio -p 8765:8765 \
        -e OSP_INPUT_FILE=- osp-decoder:latest "$@"
