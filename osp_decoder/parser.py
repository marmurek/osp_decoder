"""Interpretation of multimon-ng output lines."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .events import Detection

# Five-tone demodulators that print a whole sequence as "NAME: digits".
_SELCALL_RE = re.compile(r"^(ZVEI1|ZVEI2|ZVEI3|DZVEI|PZVEI|EEA|EIA|CCIR): ([0-9A-F]+)$")


@dataclass(frozen=True)
class DtmfDigit:
    """A single DTMF digit; multimon-ng reports DTMF digit by digit."""

    digit: str


def parse_line(line: str) -> Detection | DtmfDigit | None:
    """Parse one line of multimon-ng output; unknown lines yield None."""
    line = line.strip()
    if line.startswith("{"):
        return _parse_json(line)
    match = _SELCALL_RE.match(line)
    if match:
        return Detection(protocol=match.group(1).lower(), sequence=match.group(2))
    return None


def _parse_json(line: str) -> Detection | DtmfDigit | None:
    try:
        message: Any = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(message, dict):
        return None
    demod = message.get("demod_name")
    if demod == "STQC":
        tones = message.get("tones")
        if not isinstance(tones, str) or not tones:
            return None
        return Detection(
            protocol="stqc",
            sequence=tones,
            details={"digits": message.get("digits"), "value": message.get("value")},
        )
    if demod == "DTMF":
        digit = message.get("digit")
        if isinstance(digit, str) and len(digit) == 1:
            return DtmfDigit(digit)
    return None


class DtmfAssembler:
    """Joins DTMF digits into sequences separated by a silence timeout.

    Completed sequences are returned with the time of their last digit, which
    marks the end of detection.
    """

    def __init__(self, timeout: timedelta) -> None:
        self._timeout = timeout
        self._digits: list[str] = []
        self._last: datetime | None = None

    def add(
        self, digit: DtmfDigit, moment: datetime
    ) -> tuple[Detection, datetime] | None:
        """Add a digit; returns the previous sequence if it already timed out."""
        finished = self.poll(moment)
        self._digits.append(digit.digit)
        self._last = moment
        return finished

    def poll(self, moment: datetime) -> tuple[Detection, datetime] | None:
        """Return the pending sequence once the timeout has elapsed."""
        if self._last is None or moment - self._last < self._timeout:
            return None
        return self.flush()

    def flush(self) -> tuple[Detection, datetime] | None:
        """Return the pending sequence regardless of the timeout."""
        if not self._digits or self._last is None:
            return None
        result = Detection(protocol="dtmf", sequence="".join(self._digits)), self._last
        self._digits = []
        self._last = None
        return result
