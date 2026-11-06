"""STQC calls: pairing of address and command, and their interpretation.

The interpretation follows the format of Bartek's STQC decoder v2.16
(https://serwerbartka.pl/dekoder-stqc/) as documented by AirKeyooo in
https://github.com/airkey037/stqc_docs (GPL-3.0). The format is community
knowledge, not published by the manufacturer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .events import Detection
from .names import NamesFile

ADDRESS_TONES = 7
COMMAND_TONES = 8
# Addresses are also accepted without their first tone, which a late opening
# receiver squelch can cut. Address values with a valid area are below 4^6,
# so the first digit is 0, sent as tone 4, and losing it keeps the value.
# The command follows while the carrier is still on and keeps all tones.
ADDRESS_LENGTHS = (ADDRESS_TONES - 1, ADDRESS_TONES)

# Command names indexed by the command code.
COMMANDS = (
    "KASUJ",
    "ALARM",
    "PAGER",
    "TEST",
    "MAKRO",
    "OC.GR",
    "AI.OC1",
    "AI.OC2",
    "AI.OC3",
    "FONIA",
)

# Upper bound of the 6-bit parts of an area number.
_SIX_BITS = 63


@dataclass(frozen=True)
class Call:
    """An address sequence followed by a command sequence."""

    address: Detection
    command: Detection
    address_value: int
    command_value: int


def _value(detection: Detection) -> int | None:
    value = detection.details.get("value")
    return value if isinstance(value, int) else None


def interpret(address: int, command: int) -> dict[str, Any]:
    """Interpret address and command values in the format of decoder v2.16.

    The command carries the unit (value mod 1000) and the command code
    (value div 1000). The address holds two 6-bit numbers (value div 64 and
    value mod 64), written as a 4-digit area number, e.g. 32 and 27 as 3227.
    Fields outside their documented range are reported as None.
    """
    code = command // 1000
    high, low = divmod(address, 64)
    return {
        "area": high * 100 + low if high <= _SIX_BITS else None,
        "unit": command % 1000,
        "command_code": code,
        "command": COMMANDS[code] if code < len(COMMANDS) else None,
    }


@dataclass
class CallPairer:
    """Pairs an address (7 tones, or 6 without the first) with the command.

    A command (8 tones) completes a call only if it is detected within
    ``window`` after the address. Sequences of other lengths reset the
    pending address.
    """

    window: timedelta
    _pending: tuple[Detection, int, datetime] | None = field(default=None, init=False)

    def add(self, detection: Detection, moment: datetime) -> Call | None:
        """Feed an STQC sequence; returns a call when it completes one."""
        value = _value(detection)
        length = len(detection.sequence)
        pending, self._pending = self._pending, None
        if value is None:
            return None
        if length in ADDRESS_LENGTHS:
            self._pending = (detection, value, moment)
            return None
        if length != COMMAND_TONES or pending is None:
            return None
        address, address_value, address_moment = pending
        if moment - address_moment > self.window:
            return None
        return Call(address, detection, address_value, value)


@dataclass(frozen=True)
class InterpretedCall:
    """A call with its interpretation and, if configured, local names."""

    call: Call
    interpretation: dict[str, Any]
    names: dict[str, str | None] | None


@dataclass
class CallInterpreter:
    """Turns STQC sequences into interpreted calls."""

    pairer: CallPairer
    names: NamesFile | None = None

    def add(self, detection: Detection, moment: datetime) -> InterpretedCall | None:
        """Feed an STQC sequence; returns the call it completes, if any."""
        call = self.pairer.add(detection, moment)
        if call is None:
            return None
        interpretation = interpret(call.address_value, call.command_value)
        names = None if self.names is None else self.names.get().lookup(interpretation)
        return InterpretedCall(call, interpretation, names)
