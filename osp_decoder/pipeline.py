"""Audio source piped into multimon-ng, run as two supervised processes."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass

LOG = logging.getLogger(__name__)

# Time given to a process to exit after SIGTERM before it is killed.
TERMINATE_TIMEOUT = 3.0


@dataclass(frozen=True)
class PipelineResult:
    """Exit codes of both processes; None if a process could not start."""

    source: int | None
    decoder: int | None

    @property
    def ok(self) -> bool:
        """True when both processes exited successfully."""
        return self.source == 0 and self.decoder == 0


async def _log_stream(stream: asyncio.StreamReader, name: str) -> None:
    while line := await stream.readline():
        LOG.warning("%s: %s", name, line.decode(errors="replace").rstrip())


async def _stop(process: asyncio.subprocess.Process) -> int:
    if process.returncode is None:
        process.terminate()
        try:
            return await asyncio.wait_for(process.wait(), TERMINATE_TIMEOUT)
        except asyncio.TimeoutError:
            process.kill()
    return await process.wait()


async def run_pipeline(
    source_cmd: list[str],
    decoder_cmd: list[str],
    on_line: Callable[[str], None],
) -> PipelineResult:
    """Run ``source_cmd | decoder_cmd`` and pass decoder output lines to on_line.

    Returns when either process exits; the other one is stopped. Audio flows
    through an OS pipe between the processes and never passes through Python.
    """
    read_fd, write_fd = os.pipe()
    try:
        source = await asyncio.create_subprocess_exec(
            *source_cmd, stdout=write_fd, stderr=asyncio.subprocess.PIPE
        )
    except OSError as error:
        os.close(read_fd)
        os.close(write_fd)
        LOG.error("cannot start %s: %s", source_cmd[0], error)
        return PipelineResult(source=None, decoder=None)
    os.close(write_fd)
    try:
        decoder = await asyncio.create_subprocess_exec(
            *decoder_cmd,
            stdin=read_fd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as error:
        LOG.error("cannot start %s: %s", decoder_cmd[0], error)
        return PipelineResult(source=await _stop(source), decoder=None)
    finally:
        os.close(read_fd)

    assert source.stderr and decoder.stdout and decoder.stderr
    loggers = [
        asyncio.create_task(_log_stream(source.stderr, source_cmd[0])),
        asyncio.create_task(_log_stream(decoder.stderr, decoder_cmd[0])),
    ]
    try:
        while line := await decoder.stdout.readline():
            on_line(line.decode(errors="replace"))
    finally:
        # The decoder output ends when the decoder exits, which happens after
        # the source closes the pipe or when the decoder fails.
        decoder_code = await _stop(decoder)
        source_code = await _stop(source)
        await asyncio.gather(*loggers, return_exceptions=True)
    return PipelineResult(source=source_code, decoder=decoder_code)
