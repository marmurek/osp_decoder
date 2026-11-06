"""Tests for event construction and serialization."""

import json
from datetime import datetime, timedelta, timezone

from osp_decoder.events import (
    SCHEMA_VERSION,
    Detection,
    EventFactory,
    format_timestamp,
    to_json,
)

MOMENT = datetime(2026, 11, 5, 10, 31, 0, 120456, tzinfo=timezone.utc)


def test_timestamp_is_utc_with_milliseconds() -> None:
    """Test that timestamps are converted to UTC with millisecond precision."""
    local = MOMENT.astimezone(timezone(timedelta(hours=1)))
    assert format_timestamp(local) == "2026-11-05T10:31:00.120Z"


def test_sequence_event_fields() -> None:
    """Test that a sequence event carries the schema fields and details."""
    factory = EventFactory("radio_1")
    detection = Detection("stqc", "0204123", {"digits": "0200123", "value": 2075})
    event = factory.sequence_detected(detection, MOMENT)
    assert event["schema_version"] == SCHEMA_VERSION
    assert event["event"] == "sequence_detected"
    assert event["protocol"] == "stqc"
    assert event["sequence"] == "0204123"
    assert event["details"] == {"digits": "0200123", "value": 2075}
    assert event["source"] == "radio_1"
    assert event["run_id"] == factory.run_id
    assert event["timestamp"] == "2026-11-05T10:31:00.120Z"


def test_seq_increases_across_event_types() -> None:
    """Test that seq numbers all events of a run without gaps."""
    factory = EventFactory("radio_1")
    first = factory.status("running", "", MOMENT)
    second = factory.sequence_detected(Detection("dtmf", "12"), MOMENT)
    assert (first["seq"], second["seq"]) == (1, 2)
    assert first["event_id"] != second["event_id"]


def test_json_is_single_line_and_keeps_strings() -> None:
    """Test that serialization yields one line and keeps leading zeros."""
    event = EventFactory("radio_1").sequence_detected(
        Detection("zvei1", "00123"), MOMENT
    )
    text = to_json(event)
    assert "\n" not in text
    assert json.loads(text)["sequence"] == "00123"
