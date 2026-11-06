"""Decoder service: supervises the audio pipeline and publishes events."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .audio import (
    SOUND_CLASS,
    AudioUnavailable,
    capture_command,
    decoder_command,
    file_command,
    resolve_alsa_device,
)
from .events import Detection, EventFactory, format_timestamp, to_json
from .parser import DtmfAssembler, DtmfDigit, parse_line
from .pipeline import run_pipeline
from .publisher import Publisher
from .names import NamesFile
from .stqc import CallInterpreter, CallPairer

LOG = logging.getLogger(__name__)

# Decoder states reported in status events and by the status endpoint.
STARTING = "starting"
RUNNING = "running"
AUDIO_UNAVAILABLE = "audio_unavailable"
RESTARTING = "restarting"
STOPPED = "stopped"

DTMF_POLL_INTERVAL = 0.2


@dataclass(frozen=True)
class AudioConfig:
    """Audio input: a USB sound card, an explicit ALSA device or a file."""

    input_file: Path | None = None
    usb_id: str = "1b3f:2008"
    alsa_device: str | None = None
    sound_class: Path = SOUND_CLASS


@dataclass(frozen=True)
class DecoderConfig:
    """Demodulators and supervision of the decoding pipeline."""

    protocols: tuple[str, ...] = ("STQC",)
    multimon: str = "multimon-ng"
    dtmf_timeout: float = 1.5
    restart_delay: float = 5.0
    # Maximum time between an STQC address and its command.
    call_window: float = 2.0
    # JSON file with local names of STQC areas, units and commands.
    names_file: Path | None = None


@dataclass(frozen=True)
class ServerConfig:
    """WebSocket server address."""

    host: str = "0.0.0.0"
    port: int = 8765


@dataclass(frozen=True)
class Config:
    """Service configuration.

    With ``wait_for_receiver`` an input file is decoded only after the first
    receiver connects, so that no event of a short replay is missed.
    """

    source_name: str = "radio_1"
    audio: AudioConfig = field(default_factory=AudioConfig)
    decoder: DecoderConfig = field(default_factory=DecoderConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    wait_for_receiver: bool = False


@dataclass
class _Status:
    """Mutable state reported by the status endpoint."""

    state: str
    message: str
    since: datetime
    event_json: str
    sequences: int = 0
    restarts: int = 0
    last_detection: str | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DecoderService:
    """Runs the decoder until stopped and restarts it after failures."""

    def __init__(
        self, config: Config, clock: Callable[[], datetime] = _utc_now
    ) -> None:
        self._config = config
        self._clock = clock
        self._events = EventFactory(config.source_name)
        self._dtmf = DtmfAssembler(timedelta(seconds=config.decoder.dtmf_timeout))
        decoder = config.decoder
        names = None if decoder.names_file is None else NamesFile(decoder.names_file)
        if names is not None:
            # Report a missing or invalid file at startup, not at the first call.
            names.get()
        self._calls = CallInterpreter(
            CallPairer(timedelta(seconds=decoder.call_window)), names
        )
        self.publisher = Publisher(
            config.server.host,
            config.server.port,
            self.status,
            lambda: self._status.event_json,
        )
        since = clock()
        self._status = _Status(
            state=STARTING,
            message="",
            since=since,
            event_json=to_json(self._events.status(STARTING, "", since)),
        )

    def status(self) -> dict[str, Any]:
        """Current state and counters, served on the status endpoint."""
        return {
            "state": self._status.state,
            "message": self._status.message,
            "since": format_timestamp(self._status.since),
            "source": self._config.source_name,
            "run_id": self._events.run_id,
            "receivers": self.publisher.receivers,
            "sequences": self._status.sequences,
            "restarts": self._status.restarts,
            "last_detection": self._status.last_detection,
        }

    def _set_state(self, state: str, message: str) -> None:
        status = self._status
        if state == status.state and message == status.message:
            return
        status.state, status.message, status.since = state, message, self._clock()
        LOG.info("state %s: %s", state, message)
        # Receivers that connect later get this event again with the same seq,
        # so the snapshot does not create a gap in the sequence numbers.
        status.event_json = to_json(self._events.status(state, message, status.since))
        self.publisher.publish(status.event_json)

    def _emit(self, detection: Detection, moment: datetime) -> None:
        self._status.sequences += 1
        self._status.last_detection = format_timestamp(moment)
        LOG.info("detected %s %s", detection.protocol, detection.sequence)
        self.publisher.publish(
            to_json(self._events.sequence_detected(detection, moment))
        )
        if detection.protocol != "stqc":
            return
        result = self._calls.add(detection, moment)
        if result is None:
            return
        call, interpretation = result.call, result.interpretation
        LOG.info(
            "call %s/%s: %s unit %s %s",
            call.address_value,
            call.command_value,
            interpretation["command"],
            interpretation["unit"],
            result.names or "",
        )
        self.publisher.publish(to_json(self._events.call_detected(result, moment)))

    def _on_line(self, line: str) -> None:
        parsed = parse_line(line)
        moment = self._clock()
        if isinstance(parsed, Detection):
            self._emit(parsed, moment)
        elif isinstance(parsed, DtmfDigit):
            finished = self._dtmf.add(parsed, moment)
            if finished:
                self._emit(*finished)
        elif line.strip():
            LOG.debug("ignored decoder output: %s", line.rstrip())

    def _flush_dtmf(self) -> None:
        finished = self._dtmf.flush()
        if finished:
            self._emit(*finished)

    async def _poll_dtmf(self) -> None:
        while True:
            await asyncio.sleep(DTMF_POLL_INTERVAL)
            finished = self._dtmf.poll(self._clock())
            if finished:
                self._emit(*finished)

    def _source_command(self) -> list[str]:
        audio = self._config.audio
        if audio.input_file is not None:
            return file_command(audio.input_file)
        device = resolve_alsa_device(audio.usb_id, audio.alsa_device, audio.sound_class)
        return capture_command(device)

    async def run(self, stop: asyncio.Event) -> None:
        """Decode until ``stop`` is set or the input file ends."""
        await self.publisher.start()
        poller = asyncio.create_task(self._poll_dtmf())
        try:
            if (
                self._config.audio.input_file is not None
                and self._config.wait_for_receiver
            ):
                while self.publisher.receivers == 0 and not stop.is_set():
                    await asyncio.sleep(0.1)
            while not stop.is_set():
                if not await self._run_once(stop):
                    break
                if await _wait(stop, self._config.decoder.restart_delay):
                    break
        finally:
            poller.cancel()
            self._flush_dtmf()
            self._set_state(STOPPED, "service stopped")
            await self.publisher.stop()

    async def _run_once(self, stop: asyncio.Event) -> bool:
        """Run the pipeline once; returns False when the service should end."""
        try:
            source_cmd = self._source_command()
        except AudioUnavailable as error:
            self._set_state(AUDIO_UNAVAILABLE, str(error))
            return True
        decoder_cmd = decoder_command(
            list(self._config.decoder.protocols), self._config.decoder.multimon
        )
        self._set_state(RUNNING, " ".join(source_cmd))
        pipeline = asyncio.create_task(
            run_pipeline(source_cmd, decoder_cmd, self._on_line)
        )
        stopper = asyncio.create_task(stop.wait())
        await asyncio.wait({pipeline, stopper}, return_when=asyncio.FIRST_COMPLETED)
        stopper.cancel()
        if not pipeline.done():
            pipeline.cancel()
            await asyncio.gather(pipeline, return_exceptions=True)
            return False
        result = pipeline.result()
        self._flush_dtmf()
        if self._config.audio.input_file is not None:
            return False
        self._status.restarts += 1
        self._set_state(
            RESTARTING,
            f"pipeline exited (source {result.source}, decoder {result.decoder})",
        )
        return True


async def _wait(stop: asyncio.Event, seconds: float) -> bool:
    """Wait up to ``seconds``; returns True if ``stop`` was set."""
    try:
        await asyncio.wait_for(stop.wait(), seconds)
    except asyncio.TimeoutError:
        return False
    return True
