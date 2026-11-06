# Raspberry Pi deployment

Steps to run the decoder on a Raspberry Pi with the USB sound card. This
procedure has not been tested on hardware yet.

## Hardware and system

- Raspberry Pi 2, 3, 4 or 5. Raspberry Pi 1 and Zero (ARMv6) are not covered:
  Docker does not provide packages for them.
- 32-bit (`armhf`, image `linux/arm/v7`) or 64-bit (`arm64`) operating system:
  Raspberry Pi OS Lite or DietPi. 64-bit is preferred on boards that support
  it (Pi 3 and newer).
- GeneralPlus USB sound card (`1b3f:2008`), connected as described in
  [audio-input.md](audio-input.md).
- Network access for the receivers and for time synchronization.

## 1. Install the system

1. Write Raspberry Pi OS Lite (or DietPi) to the SD card, for example with
   Raspberry Pi Imager, and enable SSH.
2. Log in and update the system:

   ```bash
   sudo apt update && sudo apt full-upgrade -y
   ```

3. Check that the clock is synchronized; event timestamps come from the
   system clock:

   ```bash
   timedatectl
   ```

   `System clock synchronized: yes` is required. Raspberry Pi has no
   real-time clock, so the time is wrong until NTP succeeds after boot.

## 2. Install Docker

On Raspberry Pi OS:

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker "$USER"
```

Log out and in again, then check:

```bash
docker version
docker compose version
```

On DietPi, install Docker and Docker Compose with `dietpi-software` instead.

Docker starts at boot; the decoder container is restarted automatically
(`restart: unless-stopped` in [compose.yaml](../compose.yaml)).

## 3. Check the sound card

Connect the card and check that the system sees it:

```bash
lsusb | grep 1b3f:2008
cat /sys/class/sound/card*/id
arecord -l
```

`arecord` is in the `alsa-utils` package (`sudo apt install alsa-utils`).

Set the input level with `alsamixer -c Device` (F4 shows capture controls):
lower `Mic` capture well below 100% and keep `Auto Gain Control` off. Save the
settings so that they survive a reboot:

```bash
sudo alsactl store
```

The correct level is checked in step 6.

## 4. Get the project and build the image

```bash
git clone https://github.com/marmurek/osp_decoder.git
cd osp_decoder
docker compose build
```

The build compiles multimon-ng on the Pi and takes several minutes; later
builds reuse the cached layers.

Building on a PC instead requires emulation of the Pi's architecture
(`docker buildx` with QEMU) and transferring the image, for example:

```bash
docker buildx build --platform linux/arm64 --target runtime -t osp-decoder:latest --output type=docker,dest=osp-decoder.tar .
scp osp-decoder.tar pi@raspberrypi:
ssh pi@raspberrypi docker load -i osp-decoder.tar
```

Use `linux/arm/v7` for a 32-bit system.

## 5. Configure and start

Settings are environment variables in [compose.yaml](../compose.yaml), for
example the source name and the enabled protocols:

```yaml
    environment:
      OSP_SOURCE_NAME: radio_1
      OSP_PROTOCOLS: STQC
```

All options are listed in the [README](../README.md#configuration). Start the
decoder:

```bash
docker compose up -d
docker compose ps
curl http://localhost:8765/status
```

The status must be `running` and `docker compose ps` must show the container
as `healthy`. `audio_unavailable` means the card was not found; the decoder
retries every 5 seconds.

## 6. Verify decoding

Watch the events on the Pi:

```bash
scripts/monitor.sh
```

or from another computer on the network:

```bash
scripts/monitor.sh ws://raspberrypi:8765/
```

Then check the audio path:

1. With the radio tuned to the channel, wait for a call or a test call and
   confirm that `stqc` events appear.
2. Check the level: a short recording of a call (stop the decoder first,
   because the card can only be opened once):

   ```bash
   docker compose stop
   arecord -D plughw:CARD=Device -f S16_LE -c 1 -r 22050 -d 30 test.wav
   docker compose start
   ```

   Copy `test.wav` to a PC and check the peaks (around −6 dBFS, no clipping).
   It can be replayed on the PC with `scripts/replay.sh test.wav`.

## 7. Operation

| Task | Command |
|---|---|
| Logs | `docker compose logs -f` |
| Status | `curl http://localhost:8765/status` |
| Restart | `docker compose restart` |
| Update | `git pull && docker compose up -d --build` |
| Stop | `docker compose down` |

Container logs are limited to 3 files of 1 MB to limit SD card wear. The
decoder does not store events; receivers that need history must store them.

The WebSocket port 8765 is not authenticated or encrypted. Expose it only on
a trusted network, or restrict access with a firewall.
