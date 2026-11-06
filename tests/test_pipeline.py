"""Tests for the supervised source | decoder process pair."""

import asyncio
import sys

from osp_decoder.pipeline import PipelineResult, run_pipeline

PY = sys.executable

# Writes 10000 bytes of audio and exits.
SOURCE_FINITE = [PY, "-c", "import sys; sys.stdout.buffer.write(bytes(10000))"]
# Writes audio until the pipe closes.
SOURCE_ENDLESS = [
    PY,
    "-c",
    "import sys\nwhile True: sys.stdout.buffer.write(bytes(4096))",
]
# Prints a line, counts the input bytes until EOF and prints the count.
DECODER_COUNT = [
    PY,
    "-c",
    "import sys; print('start', flush=True); print(len(sys.stdin.buffer.read()))",
]
DECODER_FAIL = [PY, "-c", "import sys; print('bad', file=sys.stderr); sys.exit(3)"]


def _run(source: list[str], decoder: list[str]) -> tuple[PipelineResult, list[str]]:
    lines: list[str] = []
    result = asyncio.run(run_pipeline(source, decoder, lines.append))
    return result, lines


def test_audio_flows_from_source_to_decoder() -> None:
    """Test that all audio reaches the decoder and its lines are passed on."""
    result, lines = _run(SOURCE_FINITE, DECODER_COUNT)
    assert result.ok
    assert [line.strip() for line in lines] == ["start", "10000"]


def test_decoder_failure_stops_source() -> None:
    """Test that a failing decoder ends the pipeline and stops the source."""
    result, lines = _run(SOURCE_ENDLESS, DECODER_FAIL)
    assert result.decoder == 3
    assert result.source is not None and result.source != 0
    assert not result.ok
    assert not lines


def test_missing_source_executable() -> None:
    """Test that a source that cannot start is reported without a decoder."""
    result, _ = _run(["/nonexistent/arecord"], DECODER_COUNT)
    assert result == PipelineResult(source=None, decoder=None)


def test_missing_decoder_executable() -> None:
    """Test that a decoder that cannot start stops the running source."""
    result, _ = _run(SOURCE_ENDLESS, ["/nonexistent/multimon-ng"])
    assert result.decoder is None
    assert result.source is not None
