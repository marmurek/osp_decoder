"""End-to-end tests with real multimon-ng and gen-ng signals (dev image)."""

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from websockets.asyncio.client import connect

from osp_decoder.service import (
    AudioConfig,
    Config,
    DecoderConfig,
    DecoderService,
    ServerConfig,
)

pytestmark = pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("multimon-ng", "gen-ng", "sox")),
    reason="requires multimon-ng, gen-ng and sox",
)


def _generate(path: Path, *options: str) -> Path:
    # A silent 1 s sine generator pads the signal, so that the decoder closes
    # the last sequence by timeout before the input ends.
    subprocess.run(
        ["gen-ng", "-t", "wav", *options, "-s", "1000", "-a", "0", str(path)],
        check=True,
        capture_output=True,
    )
    return path


async def _replay(
    audio: Path, protocols: tuple[str, ...], kind: str = "sequence_detected"
) -> list[Any]:
    service = DecoderService(
        Config(
            audio=AudioConfig(input_file=audio),
            decoder=DecoderConfig(protocols=protocols),
            server=ServerConfig(host="127.0.0.1", port=0),
            wait_for_receiver=True,
        )
    )
    runner = asyncio.create_task(service.run(asyncio.Event()))
    while service.publisher.port == 0:
        await asyncio.sleep(0.01)
    async with connect(f"ws://127.0.0.1:{service.publisher.port}/") as client:
        events = [json.loads(message) async for message in client]
    await runner
    if kind == "sequence_detected":
        return [
            (e["protocol"], e["sequence"], e["details"])
            for e in events
            if e["event"] == kind
        ]
    return [e for e in events if e["event"] == kind]


@pytest.mark.parametrize(
    "tones", ["4012012 40104324 ", "012012 40104324 "], ids=["full", "first-tone-cut"]
)
def test_generated_call_is_interpreted(tmp_path: Path, tones: str) -> None:
    """Test that an address followed by a command yields a call event."""
    audio = _generate(tmp_path / "call.wav", "-Q", tones)
    calls = asyncio.run(_replay(audio, ("STQC",), "call_detected"))
    assert len(calls) == 1
    interpretation = calls[0]["interpretation"]
    assert (interpretation["command"], interpretation["unit"]) == ("ALARM", 82)
    assert interpretation["area"] == 606


@pytest.mark.parametrize(
    "options, protocols, expected",
    [
        (
            ("-Q", "4204123 40324202 "),
            ("STQC",),
            [
                ("stqc", "4204123", {"digits": "0200123", "value": 2075}),
                ("stqc", "40324202", {"digits": "00322202", "value": 3746}),
            ],
        ),
        (("-d", "0123#"), ("DTMF",), [("dtmf", "0123#", {})]),
        (("-d", "*1122#"), ("DTMF",), [("dtmf", "*1122#", {})]),
        (("-d", "456789ABCD"), ("DTMF",), [("dtmf", "456789ABCD", {})]),
        (("-z", "01234"), ("ZVEI1",), [("zvei1", "01234", {})]),
    ],
)
def test_generated_signal(
    tmp_path: Path,
    options: tuple[str, ...],
    protocols: tuple[str, ...],
    expected: list[Any],
) -> None:
    """Test that generated signals arrive as events with raw sequences."""
    audio = _generate(tmp_path / "signal.wav", *options)
    assert asyncio.run(_replay(audio, protocols)) == expected
