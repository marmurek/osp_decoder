"""Audio sources and the multimon-ng command line."""

from __future__ import annotations

from pathlib import Path

# Native input rate of multimon-ng in raw mode.
SAMPLE_RATE = 22050

# sysfs is used instead of /proc/asound, which Docker masks in containers.
SOUND_CLASS = Path("/sys/class/sound")


class AudioUnavailable(Exception):
    """The configured audio device is not present."""


def find_card_id(usb_id: str, sound_class: Path = SOUND_CLASS) -> str | None:
    """Return the ALSA card id of the USB device with the given VID:PID.

    Card numbers change when devices are re-plugged; the USB id and the card
    id stay stable. A card's ``device`` link points to the USB interface,
    whose parent directory holds the vendor and product ids.
    """
    wanted = usb_id.strip().lower()
    for card in sorted(sound_class.glob("card[0-9]*")):
        try:
            usb_device = (card / "device").resolve().parent
            vendor = (usb_device / "idVendor").read_text(encoding="ascii").strip()
            product = (usb_device / "idProduct").read_text(encoding="ascii").strip()
            if f"{vendor}:{product}".lower() == wanted:
                return (card / "id").read_text(encoding="ascii").strip()
        except OSError:
            continue
    return None


def resolve_alsa_device(
    usb_id: str, device: str | None = None, sound_class: Path = SOUND_CLASS
) -> str:
    """Return the ALSA capture device, preferring an explicit device name."""
    if device:
        return device
    card = find_card_id(usb_id, sound_class)
    if card is None:
        raise AudioUnavailable(f"no sound card with USB id {usb_id}")
    # plughw converts the hardware rate (44.1/48 kHz) to SAMPLE_RATE.
    return f"plughw:CARD={card},DEV=0"


def capture_command(device: str) -> list[str]:
    """Command that writes mono raw audio from an ALSA device to stdout."""
    return [
        "arecord",
        "--quiet",
        "--device",
        device,
        "--format",
        "S16_LE",
        "--channels",
        "1",
        "--rate",
        str(SAMPLE_RATE),
        "--file-type",
        "raw",
    ]


# Input file name that selects raw audio on standard input.
STDIN = Path("-")


def file_command(path: Path) -> list[str]:
    """Command that writes an audio file as mono raw audio to stdout.

    For ``-`` the service's standard input is passed through unchanged; it
    must already be mono S16_LE raw audio at SAMPLE_RATE.
    """
    if path == STDIN:
        return ["cat"]
    return [
        "sox",
        "--no-show-progress",
        str(path),
        "--type",
        "raw",
        "--encoding",
        "signed-integer",
        "--bits",
        "16",
        "--endian",
        "little",
        "--channels",
        "1",
        "--rate",
        str(SAMPLE_RATE),
        "-",
    ]


def decoder_command(protocols: list[str], executable: str = "multimon-ng") -> list[str]:
    """Command that decodes raw audio from stdin with the given demodulators."""
    command = [executable, "-q", "-t", "raw", "--json"]
    for protocol in protocols:
        command += ["-a", protocol]
    command.append("-")
    return command
