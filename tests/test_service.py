"""Tests for the decoder service with a fake multimon-ng."""

import asyncio
import json
import sys
import wave
from pathlib import Path
from typing import Any

from websockets.asyncio.client import connect

from osp_decoder.__main__ import build_config, parse_args
from osp_decoder.service import (
    AudioConfig,
    Config,
    DecoderConfig,
    DecoderService,
    ServerConfig,
)

FAKE_OUTPUT = [
    "multimon-ng banner",
    '{"demod_name":"STQC","tones":"4204123","digits":"0200123","value":2075}',
    '{"demod_name":"DTMF","digit":"1"}',
    '{"demod_name":"DTMF","digit":"2"}',
    "ZVEI1: 12E45",
]


def _fake_multimon(tmp_path: Path, fail: bool = False) -> str:
    """Write an executable that prints FAKE_OUTPUT.

    It then consumes stdin until EOF, or exits with an error right away when
    ``fail`` is set.
    """
    script = tmp_path / "fake-multimon"
    lines = "\n".join(FAKE_OUTPUT)
    ending = "sys.exit(1)" if fail else "sys.stdin.buffer.read()"
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"print({lines!r}, flush=True)\n"
        f"{ending}\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return str(script)


def _silence(path: Path) -> Path:
    out = wave.Wave_write(str(path))
    try:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(22050)
        out.writeframes(bytes(22050))
    finally:
        out.close()
    return path


async def _collect(service: DecoderService, stop: asyncio.Event) -> list[Any]:
    runner = asyncio.create_task(service.run(stop))
    while service.publisher.port == 0:
        await asyncio.sleep(0.01)
    events: list[Any] = []
    async with connect(f"ws://127.0.0.1:{service.publisher.port}/") as client:
        async for message in client:
            events.append(json.loads(message))
    await runner
    return events


def test_file_replay_publishes_all_events(tmp_path: Path) -> None:
    """Test that a replayed file yields contiguous events for every protocol."""
    config = Config(
        audio=AudioConfig(input_file=_silence(tmp_path / "in.wav")),
        decoder=DecoderConfig(multimon=_fake_multimon(tmp_path)),
        server=ServerConfig(host="127.0.0.1", port=0),
        wait_for_receiver=True,
    )
    service = DecoderService(config)
    events = asyncio.run(_collect(service, asyncio.Event()))

    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    states = [e["state"] for e in events if e["event"] == "status"]
    assert states == ["starting", "running", "stopped"]
    sequences = [
        (e["protocol"], e["sequence"])
        for e in events
        if e["event"] == "sequence_detected"
    ]
    assert sequences == [("stqc", "4204123"), ("zvei1", "12E45"), ("dtmf", "12")]
    assert service.status()["sequences"] == 3


def test_missing_card_is_reported_and_retried(tmp_path: Path) -> None:
    """Test that an absent sound card is reported until the service stops."""
    config = Config(
        audio=AudioConfig(sound_class=tmp_path),
        decoder=DecoderConfig(restart_delay=0.05),
        server=ServerConfig(host="127.0.0.1", port=0),
    )
    service = DecoderService(config)

    async def scenario() -> dict[str, Any]:
        stop = asyncio.Event()
        runner = asyncio.create_task(service.run(stop))
        await asyncio.sleep(0.3)
        status = service.status()
        stop.set()
        await runner
        return status

    status = asyncio.run(scenario())
    assert status["state"] == "audio_unavailable"
    assert "1b3f:2008" in status["message"]
    assert service.status()["state"] == "stopped"


def test_failed_pipeline_is_restarted(tmp_path: Path) -> None:
    """Test that a failing decoder is restarted and counted."""
    config = Config(
        audio=AudioConfig(alsa_device="null"),
        decoder=DecoderConfig(
            multimon=_fake_multimon(tmp_path, fail=True), restart_delay=0.05
        ),
        server=ServerConfig(host="127.0.0.1", port=0),
    )
    service = DecoderService(config)

    async def scenario() -> int:
        stop = asyncio.Event()
        runner = asyncio.create_task(service.run(stop))
        while service.status()["restarts"] < 2:
            await asyncio.sleep(0.05)
        stop.set()
        await runner
        return int(service.status()["restarts"])

    assert asyncio.run(asyncio.wait_for(scenario(), 20)) >= 2


def test_command_line_options() -> None:
    """Test that command line options map onto the configuration."""
    config = build_config(
        parse_args(
            [
                "--input-file",
                "call.wav",
                "--protocols",
                "stqc, dtmf",
                "--port",
                "9000",
                "--wait-for-receiver",
            ]
        )
    )
    assert config.audio.input_file == Path("call.wav")
    assert config.decoder.protocols == ("STQC", "DTMF")
    assert config.server.port == 9000
    assert config.wait_for_receiver
