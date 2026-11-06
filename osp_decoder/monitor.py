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


def format_event(event: dict[str, Any]) -> str:
    """Render an event as one human-readable line."""
    stamp = event.get("timestamp", "?")
    if event.get("event") == "sequence_detected":
        details = event.get("details") or {}
        extra = " ".join(f"{key}={value}" for key, value in details.items())
        return f"{stamp}  {event.get('protocol')}  {event.get('sequence')}  {extra}".rstrip()
    if event.get("event") == "status":
        return f"{stamp}  status  {event.get('state')}  {event.get('message', '')}".rstrip()
    return f"{stamp}  {json.dumps(event)}"


@dataclass
class GapDetector:
    """Reports missed events from gaps in ``seq`` within one ``run_id``."""

    run_id: str | None = None
    seq: int | None = None

    def check(self, event: dict[str, Any]) -> str | None:
        """Return a warning when events between the previous and this one are missing."""
        run_id, seq = event.get("run_id"), event.get("seq")
        if not isinstance(seq, int):
            return None
        warning = None
        if run_id != self.run_id:
            if self.run_id is not None:
                warning = "decoder restarted (new run_id)"
        elif self.seq is not None and seq > self.seq + 1:
            warning = f"missed {seq - self.seq - 1} event(s)"
        self.run_id, self.seq = run_id if isinstance(run_id, str) else None, seq
        return warning


async def monitor(url: str, raw: bool, output: Callable[[str], None] = print) -> None:
    """Print events from ``url`` and reconnect whenever the connection drops."""
    gaps = GapDetector()
    while True:
        try:
            async with connect(url) as connection:
                output(f"connected to {url}")
                async for message in connection:
                    event = json.loads(message)
                    warning = gaps.check(event)
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
