"""Tests for multimon-ng output parsing and DTMF assembly."""

from datetime import datetime, timedelta, timezone

import pytest

from osp_decoder.events import Detection
from osp_decoder.parser import DtmfAssembler, DtmfDigit, parse_line

START = datetime(2026, 11, 5, 10, 0, 0, tzinfo=timezone.utc)


def test_stqc_json() -> None:
    """Test that an STQC JSON line yields tones, digits and value."""
    line = '{"demod_name":"STQC","tones":"4204123","digits":"0200123","value":2075}\n'
    assert parse_line(line) == Detection(
        "stqc", "4204123", {"digits": "0200123", "value": 2075}
    )


@pytest.mark.parametrize(
    "line, expected",
    [
        ("ZVEI1: 12E45", Detection("zvei1", "12E45")),
        ("ZVEI2: 00123\n", Detection("zvei2", "00123")),
        ("CCIR: 7", Detection("ccir", "7")),
    ],
)
def test_selcall_text(line: str, expected: Detection) -> None:
    """Test that five-tone text lines keep the raw sequence."""
    assert parse_line(line) == expected


@pytest.mark.parametrize("digit", list("0123456789*#ABCD"))
def test_dtmf_digit(digit: str) -> None:
    """Test that a DTMF JSON line yields a single digit for all 16 symbols."""
    line = f'{{"demod_name":"DTMF","digit":"{digit}"}}'
    assert parse_line(line) == DtmfDigit(digit)


@pytest.mark.parametrize(
    "line",
    [
        "",
        "multimon-ng 1.6.2",
        "ZVEI1: ",
        "{not json",
        "[1, 2]",
        '{"demod_name":"STQC","tones":""}',
        '{"demod_name":"DTMF","digit":"12"}',
        '{"demod_name":"POCSAG1200"}',
    ],
)
def test_ignored_lines(line: str) -> None:
    """Test that unrelated or malformed lines are ignored."""
    assert parse_line(line) is None


def test_dtmf_sequence_ends_after_timeout() -> None:
    """Test that digits form one sequence timestamped by the last digit."""
    assembler = DtmfAssembler(timedelta(seconds=1))
    assert assembler.add(DtmfDigit("1"), START) is None
    assert assembler.add(DtmfDigit("2"), START + timedelta(seconds=0.5)) is None
    assert assembler.poll(START + timedelta(seconds=1.4)) is None
    finished = assembler.poll(START + timedelta(seconds=1.5))
    assert finished == (Detection("dtmf", "12"), START + timedelta(seconds=0.5))
    assert assembler.poll(START + timedelta(seconds=5)) is None


def test_dtmf_repeated_digits_are_kept() -> None:
    """Test that repeated digits within the timeout stay in one sequence."""
    assembler = DtmfAssembler(timedelta(seconds=1))
    for index, digit in enumerate("*1122#"):
        moment = START + timedelta(seconds=0.1 * index)
        assert assembler.add(DtmfDigit(digit), moment) is None
    assert assembler.flush() == (
        Detection("dtmf", "*1122#"),
        START + timedelta(seconds=0.5),
    )


def test_dtmf_late_digit_starts_new_sequence() -> None:
    """Test that a digit after the timeout closes the previous sequence."""
    assembler = DtmfAssembler(timedelta(seconds=1))
    assembler.add(DtmfDigit("1"), START)
    finished = assembler.add(DtmfDigit("2"), START + timedelta(seconds=2))
    assert finished == (Detection("dtmf", "1"), START)
    assert assembler.flush() == (
        Detection("dtmf", "2"),
        START + timedelta(seconds=2),
    )
    assert assembler.flush() is None
