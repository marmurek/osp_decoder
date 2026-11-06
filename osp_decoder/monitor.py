"""Console receiver that prints events from a running decoder."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

RECONNECT_DELAY = 2.0


def _named(text: str, name: Any) -> str:
    return f"{text} ({name})" if name else text


def _format_interpretation(
    interpretation: dict[str, Any], names: dict[str, Any]
) -> str:
    command = interpretation.get("command") or (
        f"command {interpretation.get('command_code')}"
    )
    parts = [
        _named(command, names.get("command"))
        + " "
        + _named(f"unit {interpretation.get('unit')}", names.get("unit"))
    ]
    area = interpretation.get("area")
    if area is not None:
        parts.append(_named(f"area {area}", names.get("area")))
    return " | ".join(parts)


def format_event(event: dict[str, Any]) -> str:
    """Render an event as one human-readable line."""
    stamp = event.get("timestamp", "?")
    if event.get("event") == "call_detected":
        address = (event.get("address") or {}).get("value")
        command = (event.get("command") or {}).get("value")
        text = _format_interpretation(
            event.get("interpretation") or {}, event.get("names") or {}
        )
        return f"{stamp}  {event.get('protocol')} call  {address}/{command}  {text}"
    if event.get("event") == "sequence_detected":
        details = event.get("details") or {}
        extra = " ".join(f"{key}={value}" for key, value in details.items())
        return f"{stamp}  {event.get('protocol')}  {event.get('sequence')}  {extra}".rstrip()
    if event.get("event") == "status":
        return f"{stamp}  status  {event.get('state')}  {event.get('message', '')}".rstrip()
    return f"{stamp}  {json.dumps(event)}"


@dataclass
class GapDetector:
    """Reports missed events from gaps in ``seq`` within one ``run_id``.

    The status event sent right after connecting repeats an earlier event with
    its original ``seq``; it only identifies the run and is not used as the
    reference, so events published before the receiver connected are not
    reported as missed. After a reconnect the first live event is compared
    with the last one received before, which reveals events lost meanwhile.
    """

    run_id: str | None = None
    seq: int | None = None

    def check(self, event: dict[str, Any], snapshot: bool = False) -> str | None:
        """Return a warning when events were missed before this one."""
        run_id, seq = event.get("run_id"), event.get("seq")
        if not isinstance(run_id, str) or not isinstance(seq, int):
            return None
        if run_id != self.run_id:
            warning = None if self.run_id is None else "decoder restarted (new run_id)"
            self.run_id, self.seq = run_id, None if snapshot else seq
            return warning
        if snapshot:
            return None
        warning = None
        if self.seq is not None and seq > self.seq + 1:
            warning = f"missed {seq - self.seq - 1} event(s)"
        if self.seq is None or seq > self.seq:
            self.seq = seq
        return warning


async def monitor(url: str, raw: bool, output: Callable[[str], None] = print) -> None:
    """Print events from ``url`` and reconnect whenever the connection drops."""
    gaps = GapDetector()
    while True:
        try:
            async with connect(url) as connection:
                output(f"connected to {url}")
                first = True
                async for message in connection:
                    try:
                        event = json.loads(message)
                    except ValueError:
                        event = None
                    if not isinstance(event, dict):
                        output(f"!! not an event: {message!r}")
                        continue
                    warning = gaps.check(event, snapshot=first)
                    first = False
                    if warning:
                        output(f"!! {warning}")
                    output(str(message) if raw else format_event(event))
        except (OSError, WebSocketException) as error:
            output(f"disconnected: {error}; retrying in {RECONNECT_DELAY:.0f} s")
        await asyncio.sleep(RECONNECT_DELAY)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the console receiver until interrupted."""
    parser = argparse.ArgumentParser(
        prog="osp-monitor", description="Print events from an OSP decoder."
    )
    parser.add_argument("url", nargs="?", default="ws://localhost:8765/")
    parser.add_argument("--raw", action="store_true", help="print events as JSON")
    args = parser.parse_args(argv)
    try:
        asyncio.run(monitor(args.url, args.raw))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
