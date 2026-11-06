"""Tests for the local names file."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from osp_decoder.names import NamesError, NamesFile, parse_names
from osp_decoder.stqc import interpret

EXAMPLE = Path(__file__).parent.parent / "examples" / "names.example.json"


def _write(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_example_file_lookup() -> None:
    """Test that the shipped example resolves area, unit and command names."""
    names = NamesFile(EXAMPLE).get()
    # Address 586 is area 910; command 1060 is ALARM, unit 60.
    assert names.lookup(interpret(586, 1060)) == {
        "area": "Example county",
        "unit": "OSP Example North",
        "command": "Fire alarm",
    }


def test_unknown_entries_are_none() -> None:
    """Test that missing areas, units and commands yield None."""
    names = NamesFile(EXAMPLE).get()
    assert names.lookup(interpret(586, 4099)) == {
        "area": "Example county",
        "unit": None,
        "command": None,
    }
    assert names.lookup(interpret(2075, 3746))["area"] is None
    assert names.lookup(interpret(16383, 1060)) == {
        "area": None,
        "unit": None,
        "command": "Fire alarm",
    }


@pytest.mark.parametrize("key", ["910", "0910"])
def test_area_keys_with_leading_zeros(key: str) -> None:
    """Test that area keys copied with leading zeros still match."""
    names = parse_names({"areas": {key: {"name": "Area", "units": {"060": "U"}}}})
    assert names.lookup(interpret(586, 1060))["area"] == "Area"
    assert names.lookup(interpret(586, 1060))["unit"] == "U"


def test_names_are_single_line() -> None:
    """Test that line breaks and repeated spaces in names are collapsed."""
    names = parse_names({"areas": {"910": {"name": " OSP Grodzisko\n  Dolne "}}})
    assert names.areas == {910: "OSP Grodzisko Dolne"}


def test_byte_order_mark_is_accepted(tmp_path: Path) -> None:
    """Test that a file saved as UTF-8 with BOM is read."""
    path = tmp_path / "names.json"
    path.write_bytes(
        b"\xef\xbb\xbf" + json.dumps({"areas": {"910": {"name": "Area"}}}).encode()
    )
    assert NamesFile(path).get().areas == {910: "Area"}


def test_out_of_range_area_has_no_names() -> None:
    """Test that a call without a valid area gets no area or unit name."""
    names = parse_names({"areas": {"910": {"name": "Area", "units": {"60": "U"}}}})
    assert names.lookup(interpret(16383, 1060)) == {
        "area": None,
        "unit": None,
        "command": None,
    }


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"commands": {"x": "name"}},
        {"commands": {"1": 5}},
        {"areas": {"910": "name"}},
        {"areas": {"910": {"name": 1}}},
        {"areas": {"910": {"units": {"sixty": "OSP"}}}},
        {"areas": {"910": {"units": []}}},
        {"areas": {"Lezajsk": {"name": "x"}}},
        {"areas": {"9:10": {"name": "x"}}},
        {"area": {"910": {"name": "x"}}},
    ],
)
def test_invalid_structure(data: Any) -> None:
    """Test that structural errors are rejected."""
    with pytest.raises(NamesError):
        parse_names(data)


def test_reload_on_change_and_keep_last_valid(tmp_path: Path) -> None:
    """Test that edits are picked up and invalid edits keep the last names."""
    path = _write(tmp_path / "names.json", {"areas": {"910": {"name": "First"}}})
    names_file = NamesFile(path)
    assert names_file.get().areas == {910: "First"}

    _write(path, {"areas": {"910": {"name": "Second name"}}})
    os.utime(path, ns=(1, 2))
    assert names_file.get().areas == {910: "Second name"}

    path.write_text("{broken", encoding="utf-8")
    os.utime(path, ns=(3, 4))
    assert names_file.get().areas == {910: "Second name"}

    path.unlink()
    assert names_file.get().areas == {910: "Second name"}


def test_missing_file_yields_empty_names(tmp_path: Path) -> None:
    """Test that a missing file behaves like an empty one."""
    names = NamesFile(tmp_path / "absent.json").get()
    assert names.lookup(interpret(586, 1060)) == {
        "area": None,
        "unit": None,
        "command": None,
    }
