"""Versioned JSON events published to receivers."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .stqc import InterpretedCall

# Version 2 defines the sequence_detected, call_detected and status events.
SCHEMA_VERSION = 2


@dataclass(frozen=True)
class Detection:
    """A sequence reported by the decoder."""

    protocol: str
    sequence: str
    details: dict[str, Any] = field(default_factory=dict)


def format_timestamp(moment: datetime) -> str:
    """Format a timestamp as UTC ISO 8601 with milliseconds and a Z suffix."""
    utc = moment.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


@dataclass
class EventFactory:
    """Builds events with a per-run sequence number for loss detection.

    ``seq`` increases by one for every event of a run; a gap tells a receiver
    that it missed events. ``run_id`` changes on every start of the decoder,
    which resets ``seq``.
    """

    source: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    _seq: int = 0

    def _base(self, event: str, moment: datetime) -> dict[str, Any]:
        self._seq += 1
        return {
            "schema_version": SCHEMA_VERSION,
            "event": event,
            "event_id": str(uuid.uuid4()),
            "run_id": self.run_id,
            "seq": self._seq,
            "timestamp": format_timestamp(moment),
            "source": self.source,
        }

    def sequence_detected(
        self, detection: Detection, moment: datetime
    ) -> dict[str, Any]:
        """Build an event for a detected sequence."""
        event = self._base("sequence_detected", moment)
        event["protocol"] = detection.protocol
        event["sequence"] = detection.sequence
        event["details"] = dict(detection.details)
        return event

    def call_detected(
        self, result: InterpretedCall, moment: datetime
    ) -> dict[str, Any]:
        """Build an event for an STQC address followed by a command.

        ``names`` is included only when a names file is configured.
        """
        address, command = result.call.address, result.call.command
        event = self._base("call_detected", moment)
        event["protocol"] = address.protocol
        event["address"] = {
            "sequence": address.sequence,
            "value": address.details.get("value"),
        }
        event["command"] = {
            "sequence": command.sequence,
            "value": command.details.get("value"),
        }
        event["interpretation"] = result.interpretation
        if result.names is not None:
            event["names"] = result.names
        return event

    def status(self, state: str, message: str, moment: datetime) -> dict[str, Any]:
        """Build an event describing the decoder state."""
        event = self._base("status", moment)
        event["state"] = state
        event["message"] = message
        return event


def to_json(event: dict[str, Any]) -> str:
    """Serialize an event as a single line of JSON."""
    return json.dumps(event, ensure_ascii=False, separators=(",", ":"))
