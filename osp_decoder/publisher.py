"""WebSocket server broadcasting events to all connected receivers."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from http import HTTPStatus
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, broadcast, serve
from websockets.datastructures import Headers
from websockets.http11 import Request, Response

LOG = logging.getLogger(__name__)

STATUS_PATH = "/status"


class Publisher:
    """Broadcasts events to WebSocket receivers and serves the decoder status.

    Receivers get every event published while they are connected and nothing
    from before, except the current status sent right after connecting.
    Publishing never waits for receivers, so a slow or absent receiver cannot
    stall decoding.
    """

    def __init__(
        self,
        host: str,
        port: int,
        status: Callable[[], dict[str, Any]],
        status_event: Callable[[], str],
    ) -> None:
        self._host = host
        self._port = port
        self._status = status
        self._status_event = status_event
        self._server: Server | None = None

    async def start(self) -> None:
        """Start listening."""
        self._server = await serve(
            self._handle,
            self._host,
            self._port,
            process_request=self._process_request,
        )
        LOG.info("WebSocket server listening on %s:%d", self._host, self.port)

    async def stop(self) -> None:
        """Close all connections and stop listening."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    @property
    def port(self) -> int:
        """Bound port; differs from the configured one when that was 0."""
        if self._server is None:
            return self._port
        return int(next(iter(self._server.sockets)).getsockname()[1])

    @property
    def receivers(self) -> int:
        """Number of connected receivers."""
        return 0 if self._server is None else len(self._server.connections)

    def publish(self, message: str) -> None:
        """Send a message to all connected receivers."""
        if self._server is not None:
            broadcast(self._server.connections, message)

    async def _handle(self, connection: ServerConnection) -> None:
        LOG.info("receiver connected: %s", connection.remote_address)
        await connection.send(self._status_event())
        # Incoming messages are not part of the protocol and are discarded.
        async for _ in connection:
            pass
        LOG.info("receiver disconnected: %s", connection.remote_address)

    def _process_request(
        self, _connection: ServerConnection, request: Request
    ) -> Response | None:
        """Answer plain HTTP requests for the status; others become WebSockets."""
        if request.path != STATUS_PATH:
            return None
        body = json.dumps(self._status(), separators=(",", ":")).encode()
        headers = Headers(
            [("Content-Type", "application/json"), ("Content-Length", str(len(body)))]
        )
        return Response(HTTPStatus.OK.value, HTTPStatus.OK.phrase, headers, body)
