# OSP Radio Decoder

Decodes selective calls (STQC, DTMF, ZVEI and other five-tone systems) from
radio audio captured by a sound card and publishes every detected sequence as
a JSON event to WebSocket receivers. Interpreting the sequences (which unit,
which command) is left to the receivers.

Decoding is done by [multimon-ng](https://github.com/marmurek/multimon-ng),
built from a fork that adds the STQC demodulator used by Polish volunteer fire
brigades (Digitex DSP-50, DSP-52L). See
[STQC.md](https://github.com/marmurek/multimon-ng/blob/feature/stqc/STQC.md)
for the protocol and decoder description.

## Status

| Area | State |
|---|---|
| Decoding of STQC, DTMF and ZVEI1 | verified with generated signals and STQC recordings |
| USB sound card capture in a container | verified on a PC (linux/amd64) |
| Re-plugging the sound card | handled by the restart logic; not tested with hardware |
| WebSocket events, status endpoint, health check | implemented and tested |
| Decoding audio played on the PC (desktop audio capture) | verified with replayed STQC calls on stdin |
| Raspberry Pi (linux/arm/v7, linux/arm64) | procedure documented, not tested on hardware yet |
| Recording a real radio through the sound card | not tested yet |

## Architecture

```
arecord (ALSA)   ─┐                                ┌─► WebSocket receivers
sox (file)       ─┼─ OS pipe ─► multimon-ng --json ─► osp_decoder ─┤
cat (raw stdin)  ─┘                                └─► GET /status
```

- **Audio source:** `arecord` captures mono 16-bit audio at 22050 Hz from the
  sound card (ALSA `plughw` converts from the card's 44.1/48 kHz); `sox`
  converts an audio file for replay; raw audio can also be piped in on
  standard input. Audio is never written to disk.
- **Decoder:** multimon-ng reads the audio from an OS pipe; audio does not pass
  through Python.
- **osp_decoder** (Python, asyncio):
  - supervises both processes and restarts them after a failure or when the
    sound card disappears;
  - parses multimon-ng output and joins DTMF digits into sequences;
  - builds versioned events and broadcasts them over WebSocket;
  - serves the current state on `GET /status`.

The sound card is found by its USB VID:PID (default `1b3f:2008`, GeneralPlus
USB Audio Device) in `/sys/class/sound`, so the ALSA card number may change
between restarts or re-plugging.

## Events

Each WebSocket message is one complete JSON event. The schema is
[schema/event-v1.schema.json](schema/event-v1.schema.json).

```json
{
  "schema_version": 1,
  "event": "sequence_detected",
  "event_id": "5925da92-b94e-4249-bdee-b5ee6489ce19",
  "run_id": "0ba80c8c-622d-4959-9fb7-8d7b5c24712b",
  "seq": 3,
  "timestamp": "2026-11-06T22:04:47.944Z",
  "source": "radio_1",
  "protocol": "stqc",
  "sequence": "4021042",
  "details": {"digits": "0021002", "value": 578}
}
```

```json
{
  "schema_version": 1,
  "event": "status",
  "event_id": "1730227b-9cf2-4bdd-b92f-b7435fc1b76a",
  "run_id": "0ba80c8c-622d-4959-9fb7-8d7b5c24712b",
  "seq": 2,
  "timestamp": "2026-11-06T22:04:47.939Z",
  "source": "radio_1",
  "state": "running",
  "message": "arecord --quiet --device plughw:CARD=Device,DEV=0 ..."
}
```

| Field | Meaning |
|---|---|
| `protocol` | lowercase multimon-ng demodulator name: `stqc`, `dtmf`, `zvei1`, ... |
| `sequence` | the sequence as received, always a string; leading zeros and repeat symbols (STQC tone `4`, ZVEI `E`) are kept |
| `details` | protocol-specific fields; STQC: `digits` (repeat tones resolved) and `value` (base-4 number) |
| `timestamp` | UTC time at which the decoder finished detecting the sequence (for DTMF: the last digit) |
| `seq` | increases by one for every event of a run; a gap means the receiver missed events |
| `run_id` | changes on every decoder start, when `seq` restarts at 1 |
| `state` | `starting`, `running`, `audio_unavailable`, `restarting` or `stopped` |

Delivery:

- Every connected receiver gets every event. A new receiver first gets the
  last status event (with its original `seq`) and then only new events.
- Events are not stored or repeated; a receiver that is disconnected misses
  them and can detect this from `seq`.
- Publishing never waits for receivers, so a missing or slow receiver does not
  stop decoding.

## Running on a PC

Requirements: Docker with Compose; PipeWire (`pw-record`) for decoding audio
played on the PC. Build the image once (and after every update):

```bash
docker compose build
```

Watch the events in a second terminal; the monitor reconnects by itself and
reports missed events and decoder restarts:

```bash
scripts/monitor.sh
```

Then start one of the audio sources (only one at a time, they share port
8765):

| Source | Command |
|---|---|
| Audio played on the PC, e.g. a video in the browser | `scripts/desktop-audio.sh` |
| An audio file (WAV, FLAC, MP3, ...), decoded once the monitor connects | `scripts/replay.sh samples/call.wav` |
| The USB sound card, as on the target device | `docker compose up -d` |

Desktop audio capture records everything the PC plays at the current system
volume; keep the volume moderate, as clipping reduces the decoding margin.
Extra decoder options can be added to the scripts, e.g.
`scripts/desktop-audio.sh --protocols STQC,DTMF`.

[compose.yaml](compose.yaml) mounts `/dev/snd` and allows access to all ALSA
devices, so that the sound card keeps working after it is re-plugged. The
container runs as a non-root user in the `audio` group (GID 29), restarts
automatically and is limited to 64 MB of memory.

Status and health:

```bash
curl http://localhost:8765/status
docker compose ps
```

The container health check passes only in the `running` state.

Deployment on a Raspberry Pi is described in
[docs/raspberry-pi.md](docs/raspberry-pi.md).

### Configuration

| Variable | Option | Default | Meaning |
|---|---|---|---|
| `OSP_SOURCE_NAME` | `--source-name` | `radio_1` | value of the `source` field |
| `OSP_PROTOCOLS` | `--protocols` | `STQC` | comma-separated multimon-ng demodulators, e.g. `STQC,DTMF,ZVEI1` |
| `OSP_USB_ID` | `--usb-id` | `1b3f:2008` | USB VID:PID of the sound card |
| `OSP_ALSA_DEVICE` | `--alsa-device` | | explicit ALSA capture device, overrides `OSP_USB_ID` |
| `OSP_INPUT_FILE` | `--input-file` | | decode an audio file instead of the sound card; `-` reads raw mono S16_LE 22050 Hz audio from stdin |
| `OSP_WAIT_FOR_RECEIVER` | `--wait-for-receiver` | | `1`: decode the file only after a receiver connects |
| `OSP_HOST` | `--host` | `0.0.0.0` | WebSocket listen address |
| `OSP_PORT` | `--port` | `8765` | WebSocket and status port |
| `OSP_LOG_LEVEL` | `--log-level` | `INFO` | logging level |

Each enabled demodulator adds CPU load and the chance of false detections in
noise, so only the protocols in use should be enabled.

Connecting the radio and setting the input level are described in
[docs/audio-input.md](docs/audio-input.md).

## Development

[scripts/check.sh](scripts/check.sh) builds the `dev` image (runtime plus
`gen-ng` and uv) and runs black, mypy (strict), pylint and pytest with
coverage on the mounted sources:

```bash
scripts/check.sh
```

The tests cover parsing, event construction, card lookup, process
supervision and restarts, the WebSocket server, the console monitor, and
end-to-end decoding of STQC, DTMF and ZVEI1 signals generated by `gen-ng`
through real multimon-ng.

Audio recordings are not part of the repository; `samples/` is ignored by git
and can hold local recordings for `scripts/replay.sh`.

The multimon-ng fork and commit are set by the `MULTIMON_REPO` and
`MULTIMON_REF` build arguments in the [Dockerfile](Dockerfile).

## License

Copyright (C) 2026 Wojciech Marmurowicz

This project is licensed under the GNU General Public License version 3 or
(at your option) any later version (GPL-3.0-or-later); see [LICENSE](LICENSE).
It is distributed without any warranty (sections 15 and 16 of the license).

The Docker image contains [multimon-ng](https://github.com/marmurek/multimon-ng)
(GPL-2.0-or-later) with the STQC demodulator based on the decoder by
[Jacek Lipkowski SQ5BPF](https://github.com/sq5bpf/multimon-ng-stqc).
