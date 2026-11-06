"""Tests for STQC call pairing and interpretation."""

from datetime import datetime, timedelta, timezone

import pytest

from osp_decoder.events import Detection
from osp_decoder.stqc import CallPairer, interpret

START = datetime(2026, 11, 6, 22, 0, 0, tzinfo=timezone.utc)


def _stqc(tones: str, value: int) -> Detection:
    return Detection("stqc", tones, {"digits": "", "value": value})


# Expected values cross-checked with pystqc.py from airkey037/stqc_docs:
# (address, command, unit, command name, v2.16 area).
@pytest.mark.parametrize(
    "case",
    [
        (2075, 3746, 746, "TEST", 3227),
        (578, 3225, 225, "TEST", 902),
        (1503, 1225, 225, "ALARM", 2331),
        (390, 1082, 82, "ALARM", 606),
        (390, 82, 82, "KASUJ", 606),
        (1, 9001, 1, "FONIA", 1),
    ],
)
def test_interpretation(case: tuple[int, int, int, str, int]) -> None:
    """Test the unit, command and area of a call."""
    address, command, unit, name, area = case
    assert interpret(address, command) == {
        "area": area,
        "unit": unit,
        "command_code": command // 1000,
        "command": name,
    }


def test_out_of_range_fields_are_none() -> None:
    """Test that values outside the documented ranges are not interpreted."""
    result = interpret(16383, 65535)
    assert result["command"] is None
    assert result["command_code"] == 65
    assert result["unit"] == 535
    assert result["area"] is None
    assert interpret(4095, 0)["area"] == 6363


def test_address_and_command_form_a_call() -> None:
    """Test that a command right after an address completes a call."""
    pairer = CallPairer(timedelta(seconds=2))
    address, command = _stqc("4204123", 2075), _stqc("40324202", 3746)
    assert pairer.add(address, START) is None
    call = pairer.add(command, START + timedelta(seconds=1))
    assert call is not None
    assert (call.address, call.command) == (address, command)
    assert (call.address_value, call.command_value) == (2075, 3746)
    assert pairer.add(command, START + timedelta(seconds=2)) is None


@pytest.mark.parametrize(
    "sequences",
    [
        [("40324202", 3746, 0.0)],
        [("4204123", 2075, 0.0), ("40324202", 3746, 2.5)],
        [("4204123", 2075, 0.0), ("0231", 45, 0.5), ("40324202", 3746, 1.0)],
        [("4204123", 2075, 0.0), ("40324202", None, 1.0)],
    ],
)
def test_incomplete_calls(sequences: list[tuple[str, int | None, float]]) -> None:
    """Test that lone commands, late commands and interruptions yield no call."""
    pairer = CallPairer(timedelta(seconds=2))
    results = [
        pairer.add(
            Detection("stqc", tones, {"value": value}),
            START + timedelta(seconds=offset),
        )
        for tones, value, offset in sequences
    ]
    assert results == [None] * len(sequences)


def test_address_without_first_tone_forms_a_call() -> None:
    """Test that an address cut by the squelch still pairs with the command."""
    pairer = CallPairer(timedelta(seconds=2))
    pairer.add(_stqc("204123", 2075), START)
    call = pairer.add(_stqc("40324202", 3746), START + timedelta(seconds=1))
    assert call is not None
    assert (call.address_value, call.command_value) == (2075, 3746)


def test_latest_address_is_used() -> None:
    """Test that a repeated address replaces the pending one."""
    pairer = CallPairer(timedelta(seconds=2))
    pairer.add(_stqc("4021042", 578), START)
    pairer.add(_stqc("4204123", 2075), START + timedelta(seconds=1))
    call = pairer.add(_stqc("40324202", 3746), START + timedelta(seconds=2))
    assert call is not None and call.address_value == 2075
