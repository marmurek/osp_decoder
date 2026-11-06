"""Local names for STQC areas, units and commands, read from a JSON file.

There is no public list of these names; each installation maintains its own
file. Areas are keyed by the area number of the call interpretation. Example:

    {
      "commands": {"1": "Fire alarm"},
      "areas": {
        "910": {"name": "Powiat X", "units": {"60": "OSP A", "61": "OSP B"}}
      }
    }
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)

# Top-level keys of the file; others are reported as errors to catch typos.
FILE_KEYS = ("commands", "areas")


class NamesError(ValueError):
    """The names file has an invalid structure."""


@dataclass(frozen=True)
class Names:
    """Names of areas, units within areas and commands."""

    areas: dict[int, str] = field(default_factory=dict)
    units: dict[tuple[int, int], str] = field(default_factory=dict)
    commands: dict[int, str] = field(default_factory=dict)

    def lookup(self, interpretation: dict[str, Any]) -> dict[str, str | None]:
        """Return the names of the area, unit and command of a call."""
        key = interpretation.get("area")
        key = key if isinstance(key, int) else None
        unit = interpretation.get("unit")
        code = interpretation.get("command_code")
        return {
            "area": None if key is None else self.areas.get(key),
            "unit": (
                self.units.get((key, unit))
                if key is not None and isinstance(unit, int)
                else None
            ),
            "command": self.commands.get(code) if isinstance(code, int) else None,
        }


def _number(key: str, what: str) -> int:
    try:
        return int(key)
    except ValueError:
        raise NamesError(f"{what} {key!r} is not a number") from None


def _text(value: Any, what: str) -> str:
    """Return a name with whitespace runs, including line breaks, collapsed."""
    if not isinstance(value, str):
        raise NamesError(f"{what} must be a string")
    return " ".join(value.split())


def _object(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NamesError(f"{what} must be an object")
    return value


def parse_names(data: Any) -> Names:
    """Validate the decoded JSON content of a names file."""
    root = _object(data, "the file")
    unknown = sorted(set(root) - set(FILE_KEYS))
    if unknown:
        raise NamesError(f"unknown keys {', '.join(unknown)}")
    commands = {
        _number(code, "command"): _text(name, f"command {code}")
        for code, name in _object(root.get("commands", {}), "commands").items()
    }
    areas: dict[int, str] = {}
    units: dict[tuple[int, int], str] = {}
    # Leading zeros are allowed, as in published lists (e.g. "0910").
    for raw_key, area in _object(root.get("areas", {}), "areas").items():
        key = _number(raw_key, "area")
        area = _object(area, f"area {raw_key}")
        if "name" in area:
            areas[key] = _text(area["name"], f"name of area {key}")
        for unit, name in _object(
            area.get("units", {}), f"units of area {key}"
        ).items():
            number = _number(unit, f"unit in area {key}")
            units[(key, number)] = _text(name, f"unit {unit} in area {key}")
    return Names(areas, units, commands)


@dataclass
class NamesFile:
    """Names loaded from a file and reloaded whenever the file changes.

    An unreadable or invalid file is reported once per change; the names
    loaded before stay in use, so editing the file never stops decoding.
    """

    path: Path
    _names: Names = field(default_factory=Names, init=False)
    _stamp: tuple[int, int] | None = field(default=None, init=False)

    def get(self) -> Names:
        """Return the current names, reloading the file if it changed."""
        try:
            stat = self.path.stat()
        except OSError as error:
            if self._stamp != (-1, -1):
                LOG.error("cannot read names file %s: %s", self.path, error)
                self._stamp = (-1, -1)
            return self._names
        stamp = (stat.st_mtime_ns, stat.st_size)
        if stamp != self._stamp:
            self._stamp = stamp
            try:
                # utf-8-sig also accepts files saved with a byte order mark.
                with self.path.open(encoding="utf-8-sig") as stream:
                    self._names = parse_names(json.load(stream))
                LOG.info(
                    "loaded names: %d areas, %d units, %d commands",
                    len(self._names.areas),
                    len(self._names.units),
                    len(self._names.commands),
                )
            except (OSError, ValueError) as error:
                LOG.error("invalid names file %s: %s", self.path, error)
        return self._names
