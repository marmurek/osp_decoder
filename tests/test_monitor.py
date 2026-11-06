"""Tests for the console receiver."""

import asyncio

from osp_decoder.monitor import GapDetector, format_event, monitor
from osp_decoder.publisher import Publisher

SEQUENCE = {
    "event": "sequence_detected",
    "timestamp": "2026-11-06T22:04:47.944Z",
    "protocol": "stqc",
    "sequence": "4021042",
    "details": {"digits": "0021002", "value": 578},
    "run_id": "a",
    "seq": 3,
}


def test_format_sequence_and_status() -> None:
    """Test that events render as single readable lines."""
    assert format_event(SEQUENCE) == (
        "2026-11-06T22:04:47.944Z  stqc  4021042  digits=0021002 value=578"
    )
    status = {"event": "status", "timestamp": "t", "state": "running", "message": ""}
    assert format_event(status) == "t  status  running"
    assert format_event({"event": "other"}).startswith("?  {")


def test_gap_detection_within_connection() -> None:
    """Test that missing seq numbers and restarts are reported."""
    gaps = GapDetector()
    assert gaps.check({"run_id": "a", "seq": 1}) is None
    assert gaps.check({"run_id": "a", "seq": 2}) is None
    assert gaps.check({"run_id": "a", "seq": 5}) == "missed 2 event(s)"
    assert gaps.check({"run_id": "b", "seq": 1}) == "decoder restarted (new run_id)"
    assert gaps.check({"run_id": "b", "seq": "x"}) is None


def test_snapshot_is_not_a_reference() -> None:
    """Test that events before connecting are not reported as missed."""
    gaps = GapDetector()
    assert gaps.check({"run_id": "a", "seq": 2}, snapshot=True) is None
    assert gaps.check({"run_id": "a", "seq": 43}) is None
    assert gaps.check({"run_id": "a", "seq": 44}) is None


def test_reconnect_reports_events_lost_meanwhile() -> None:
    """Test that a reconnect compares live events across the disconnection."""
    gaps = GapDetector()
    gaps.check({"run_id": "a", "seq": 2}, snapshot=True)
    gaps.check({"run_id": "a", "seq": 10})
    assert gaps.check({"run_id": "a", "seq": 2}, snapshot=True) is None
    assert gaps.check({"run_id": "a", "seq": 14}) == "missed 3 event(s)"
    assert (
        gaps.check({"run_id": "b", "seq": 1}, snapshot=True)
        == "decoder restarted (new run_id)"
    )
    assert gaps.check({"run_id": "b", "seq": 7}) is None


def test_monitor_prints_events() -> None:
    """Test that the monitor prints the snapshot and broadcast events."""

    async def scenario() -> list[str]:
        publisher = Publisher(
            "127.0.0.1", 0, dict, lambda: '{"event":"status","state":"running"}'
        )
        await publisher.start()
        lines: list[str] = []
        task = asyncio.create_task(
            monitor(f"ws://127.0.0.1:{publisher.port}/", False, lines.append)
        )
        while publisher.receivers == 0:
            await asyncio.sleep(0.01)
        publisher.publish(
            '{"event":"sequence_detected","protocol":"dtmf","sequence":"12"}'
        )
        publisher.publish("not json")
        while len(lines) < 4:
            await asyncio.sleep(0.01)
        await publisher.stop()
        while not lines[-1].startswith("disconnected"):
            await asyncio.sleep(0.01)
        task.cancel()
        return lines

    lines = asyncio.run(asyncio.wait_for(scenario(), 10))
    assert lines[0].startswith("connected to ws://127.0.0.1:")
    assert lines[1] == "?  status  running"
    assert lines[2] == "?  dtmf  12"
    assert lines[3] == "!! not an event: 'not json'"
    assert lines[-1].startswith("disconnected")
