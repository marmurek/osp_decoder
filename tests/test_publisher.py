"""Tests for the WebSocket publisher and the status endpoint."""

import asyncio
import json
import urllib.request
from typing import Any

from websockets.asyncio.client import connect

from osp_decoder.healthcheck import check
from osp_decoder.publisher import STATUS_PATH, Publisher


def _status() -> dict[str, Any]:
    return {"state": "running"}


def _http_get(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.load(response)


async def _scenario() -> tuple[list[str], list[str], Any, bool]:
    publisher = Publisher("127.0.0.1", 0, _status, lambda: '{"event":"status"}')
    await publisher.start()
    url = f"ws://127.0.0.1:{publisher.port}/"
    try:
        async with connect(url) as first, connect(url) as second:
            snapshots = [str(await first.recv()), str(await second.recv())]
            publisher.publish('{"event":"sequence_detected"}')
            received = [str(await first.recv()), str(await second.recv())]
            status = await asyncio.to_thread(
                _http_get, f"http://127.0.0.1:{publisher.port}{STATUS_PATH}"
            )
            healthy = await asyncio.to_thread(check, publisher.port)
    finally:
        await publisher.stop()
    return snapshots, received, status, healthy


def test_broadcast_and_status() -> None:
    """Test that receivers get the status snapshot and every broadcast."""
    snapshots, received, status, healthy = asyncio.run(_scenario())
    assert snapshots == ['{"event":"status"}'] * 2
    assert received == ['{"event":"sequence_detected"}'] * 2
    assert status == {"state": "running"}
    assert healthy


def test_publish_without_server_or_receivers() -> None:
    """Test that publishing never fails when nobody listens."""

    async def scenario() -> int:
        publisher = Publisher("127.0.0.1", 0, _status, lambda: "{}")
        publisher.publish("{}")
        await publisher.start()
        publisher.publish("{}")
        count = publisher.receivers
        await publisher.stop()
        return count

    assert asyncio.run(scenario()) == 0


def test_healthcheck_without_server() -> None:
    """Test that the health check fails when nothing listens."""
    assert not check(1, timeout=0.5)
