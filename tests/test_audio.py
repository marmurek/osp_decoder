"""Tests for sound card lookup and command construction."""

from pathlib import Path

import pytest

from osp_decoder.audio import (
    SAMPLE_RATE,
    AudioUnavailable,
    capture_command,
    decoder_command,
    file_command,
    find_card_id,
    resolve_alsa_device,
)


def _card(root: Path, index: int, card_id: str, usbid: str | None) -> None:
    """Create a sysfs-like card entry; USB cards link to an interface directory."""
    device = root / "devices" / f"dev{index}"
    interface = device / "1-1:1.0"
    interface.mkdir(parents=True)
    if usbid is not None:
        vendor, product = usbid.split(":")
        (device / "idVendor").write_text(vendor + "\n", encoding="ascii")
        (device / "idProduct").write_text(product + "\n", encoding="ascii")
    card = root / "class" / f"card{index}"
    card.mkdir(parents=True)
    (card / "id").write_text(card_id + "\n", encoding="ascii")
    (card / "device").symlink_to(interface)


@pytest.fixture(name="sound_class")
def fixture_sound_class(tmp_path: Path) -> Path:
    """A /sys/class/sound tree with an onboard card and the USB card as card3."""
    _card(tmp_path, 0, "NVidia", None)
    _card(tmp_path, 3, "Device", "1b3f:2008")
    (tmp_path / "class" / "controlC3").mkdir()
    return tmp_path / "class"


def test_find_card_by_usb_id(sound_class: Path) -> None:
    """Test that the card is found by USB id regardless of its number."""
    assert find_card_id("1B3F:2008", sound_class) == "Device"


def test_missing_card(sound_class: Path) -> None:
    """Test that an absent USB id yields None and AudioUnavailable."""
    assert find_card_id("dead:beef", sound_class) is None
    with pytest.raises(AudioUnavailable):
        resolve_alsa_device("dead:beef", None, sound_class)


def test_resolve_device(sound_class: Path) -> None:
    """Test that the USB card maps to plughw and an explicit device wins."""
    assert resolve_alsa_device("1b3f:2008", None, sound_class) == (
        "plughw:CARD=Device,DEV=0"
    )
    assert resolve_alsa_device("dead:beef", "hw:1,0", sound_class) == "hw:1,0"


def test_commands() -> None:
    """Test that all commands produce or consume mono raw audio at 22050 Hz."""
    rate = str(SAMPLE_RATE)
    capture = capture_command("plughw:CARD=Device,DEV=0")
    assert capture[0] == "arecord" and rate in capture and "raw" in capture
    assert file_command(Path("-")) == ["cat"]
    replay = file_command(Path("call.wav"))
    assert replay[0] == "sox" and "call.wav" in replay and replay[-1] == "-"
    assert decoder_command(["STQC", "DTMF"]) == [
        "multimon-ng",
        "-q",
        "-t",
        "raw",
        "--json",
        "-a",
        "STQC",
        "-a",
        "DTMF",
        "-",
    ]
