# OSP Radio Decoder

Decodes selective calls (STQC, DTMF, ZVEI and other five-tone systems) from
radio audio captured by a sound card and publishes every detected sequence as
a JSON event to WebSocket receivers. STQC address/command pairs are also
published as calls with an unofficial interpretation (area, unit and
command); acting on calls is left to the receivers.

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
| STQC call interpretation (area, unit, command) | implemented, cross-checked with `pystqc.py` and recordings |
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
  - pairs STQC addresses with commands and interprets the calls;
  - builds versioned events and broadcasts them over WebSocket;
  - serves the current state on `GET /status`.

The sound card is found by its USB VID:PID (default `1b3f:2008`, GeneralPlus
USB Audio Device) in `/sys/class/sound`, so the ALSA card number may change
between restarts or re-plugging.

## Events

Each WebSocket message is one complete JSON event of one of three types:
`sequence_detected`, `call_detected` and `status`. The schema is
[schema/event-v2.schema.json](schema/event-v2.schema.json); receivers should
ignore event types they do not know.

```json
{
  "schema_version": 2,
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

An STQC address (7 tones) followed within 2 s (`OSP_CALL_WINDOW`) by a command (8 tones) is
additionally published as a call, right after the command's
`sequence_detected` event. An address missing its first tone (6 tones, e.g.
cut by the receiver's squelch) is accepted as well; its value is unchanged
because that tone always encodes a leading zero for addresses with a valid
area.

```json
{
  "schema_version": 2,
  "event": "call_detected",
  "event_id": "8b0c5e1e-2a51-4f5e-9c3e-6a9b51f0a0f2",
  "run_id": "0ba80c8c-622d-4959-9fb7-8d7b5c24712b",
  "seq": 5,
  "timestamp": "2026-11-06T22:04:47.945Z",
  "source": "radio_1",
  "protocol": "stqc",
  "address": {"sequence": "4021042", "value": 578},
  "command": {"sequence": "40302423", "value": 3243},
  "interpretation": {
    "area": 902,
    "unit": 243,
    "command_code": 3,
    "command": "TEST"
  }
}
```

```json
{
  "schema_version": 2,
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

### STQC call interpretation

The numbering format is community knowledge, not published by the
manufacturer (see [Credits](#credits)); the raw `address` and `command`
values remain authoritative.

| Field | Computed from | Meaning |
|---|---|---|
| `area` | (address div 64) × 100 + address mod 64 | area number: two 6-bit numbers written as four digits, e.g. 32 and 27 as 3227; null when address div 64 exceeds 63 |
| `unit` | command value mod 1000 | unit number, 0-999 |
| `command_code`, `command` | command value div 1000 | 0 KASUJ, 1 ALARM, 2 PAGER, 3 TEST, 4 MAKRO, 5 OC.GR, 6-8 AI.OC1-3, 9 FONIA; `command` is null for other codes |

Other numbering variants in use read the address as one number (the raw
`address.value`) or as voivodeship and powiat (the two parts of `area`).

### Names of areas, units and commands

There is no public list of the names behind the numbers; each installation
keeps its own JSON file and sets `OSP_NAMES_FILE` to it. Call events then get
a `names` block, and the monitor shows the names next to the numbers:

```json
"names": {"area": "Example county", "unit": "OSP Example North", "command": "Fire alarm"}
```

```
2026-11-06T22:35:40.144Z  stqc call  586/1060  ALARM (Fire alarm) unit 60 (OSP Example North) | area 910 (Example county)
```

The file format, with fictional entries, is shown in
[examples/names.example.json](examples/names.example.json):

| Key | Meaning |
|---|---|
| `areas.<area>.name` | name of the area (area number of the interpretation) |
| `areas.<area>.units.<unit>` | name of a unit (command value mod 1000) in that area |
| `commands.<code>` | own description of a command code (0-9), in addition to KASUJ, ALARM, ... |

Area and unit keys may contain leading zeros as in published lists
(`"0910"`, `"060"`), and line breaks in names are collapsed to spaces. Files
saved as UTF-8 with or without a byte order mark are accepted. Missing entries
are `null`. The file is checked at startup and read again whenever it changes;
an invalid file is reported in the log and the previous names stay in use. Keep
the file out of public repositories (`names.json` is ignored by git), since
publishing unit numbers may be unwelcome.

Some State Fire Service commands publish "SWD" numbers of their OSP units as
seven digits, e.g. `0910060`. These fit the area format as area `910` and
unit `60`, which suggests they can be used as keys; this has not been
confirmed with a recorded call from such an area.

Delivery:

- Every connected receiver gets every event. A new receiver first gets the
  last status event (with its original `seq`) and then only new events. This
  repeated event identifies the run but must not serve as the reference for
  gap detection, or events published before connecting would count as missed.
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

Each event is one line; calls show the interpretation (`--raw` prints the
JSON instead):

```
2026-11-06T22:35:40.140Z  stqc  4143134  digits=0113133 value=1503
2026-11-06T22:35:40.144Z  stqc  40103021  digits=00103021 value=1225
2026-11-06T22:35:40.144Z  stqc call  1503/1225  ALARM unit 225 | area 2331
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
| `OSP_NAMES_FILE` | `--names-file` | | JSON file with names of STQC areas, units and commands |
| `OSP_CALL_WINDOW` | `--call-window` | `2.0` | seconds within which an STQC command must follow its address to form a call |
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

## Roadmap

Planned, not implemented yet:

- **Event history.** InfluxDB next to the decoder, in a memory-limited
  container, storing events with 14-30 days of retention. Current InfluxDB
  releases need a 64-bit system or at least ARMv7, which is to be verified
  for the chosen board; Raspberry Pi 1 is not supported.

## Development

[scripts/check.sh](scripts/check.sh) builds the `dev` image (runtime plus
`gen-ng` and uv) and runs black, mypy (strict), pylint and pytest with
coverage on the mounted sources:

```bash
scripts/check.sh
```

The tests cover parsing, event construction, card lookup, process
supervision and restarts, the WebSocket server, the console monitor, STQC
call pairing and interpretation (expected values cross-checked with
`pystqc.py`), and
end-to-end decoding of STQC, DTMF and ZVEI1 signals generated by `gen-ng`
through real multimon-ng.

Audio recordings are not part of the repository; `samples/` is ignored by git
and can hold local recordings for `scripts/replay.sh`.

The multimon-ng fork and commit are set by the `MULTIMON_REPO` and
`MULTIMON_REF` build arguments in the [Dockerfile](Dockerfile).

## Credits

- The STQC protocol description and the original STQC decoder for multimon-ng
  are by [Jacek Lipkowski SQ5BPF](https://github.com/sq5bpf/multimon-ng-stqc).
- The area, unit and command interpretation follows the format of version
  2.16 of Bartek's STQC decoder ([serwerbartka.pl](https://serwerbartka.pl/dekoder-stqc/)),
  as documented by AirKeyooo in
  [airkey037/stqc_docs](https://github.com/airkey037/stqc_docs); its
  `pystqc.py` was used to verify the implementation.
- Decoding is done by [multimon-ng](https://github.com/EliasOenal/multimon-ng)
  (Thomas Sailer, Elias Oenal and contributors).

## License

Copyright (C) 2026 Wojciech Marmurowicz

This project is licensed under the GNU General Public License version 3 or
(at your option) any later version (GPL-3.0-or-later); see [LICENSE](LICENSE).
It is distributed without any warranty (sections 15 and 16 of the license).

The Docker image contains [multimon-ng](https://github.com/marmurek/multimon-ng)
(GPL-2.0-or-later) with the STQC demodulator based on the decoder by
[Jacek Lipkowski SQ5BPF](https://github.com/sq5bpf/multimon-ng-stqc).
