"""Legacy SSE handshake support for the Streamable HTTP transport."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, Protocol
from urllib.parse import urljoin

import httpx

from .argument_schema import JsonValue
from .http_redirect import read_sse_events
from .protocol import LEGACY_PROTOCOL, MAX_FRAME, ProbeResult, ProbeStatus, ProtocolEra
from .remote_security import Resolver, validate_url


class _SseClient(Protocol):
    client: httpx.AsyncClient
    endpoint: str
    _headers: dict[str, str]
    _resolver: Resolver | None
    _max_reconnects: int
    timeout: float
    max_response: int
    last_event_id: str | None

    def request(
        self,
        method: str,
        params: dict[str, JsonValue] | None = None,
        *,
        timeout: float | None = None,
        modern_metadata: bool | None = None,
    ) -> Awaitable[ProbeResult]: ...


def _set_cursor(client: _SseClient, event_id: str) -> None:
    client.last_event_id = event_id


class SseFallbackMixin:
    async def _legacy_sse_fallback(
        self: Any, result: ProbeResult
    ) -> tuple[ProbeResult, ProtocolEra]:
        reconnects = 0
        era = ProtocolEra.MODERN
        while True:
            try:
                stream_headers = {**self._headers, "Accept": "text/event-stream"}
                if self.last_event_id:
                    stream_headers["Last-Event-ID"] = self.last_event_id
                async with self.client.stream(
                    "GET", self.endpoint, headers=stream_headers, timeout=self.timeout
                ) as stream:
                    if stream.status_code >= 400:
                        break
                    events = await read_sse_events(
                        stream, max_response=self.max_response, max_frame=MAX_FRAME
                    )
                found_endpoint = False
                for event_id, data in events:
                    if event_id:
                        if len(event_id) > 256:
                            raise ValueError("CURSOR_TOO_LARGE")
                        _set_cursor(self, event_id)
                    endpoint = data if data.startswith(("http://", "https://", "/")) else None
                    if endpoint is None:
                        continue
                    decision = validate_url(urljoin(self.endpoint, endpoint), self._resolver)
                    if decision.allowed:
                        self.endpoint = decision.transport_url
                        result = await self.request(
                            "initialize",
                            {
                                "protocolVersion": LEGACY_PROTOCOL,
                                "capabilities": {},
                                "clientInfo": {"name": "panopticon", "version": "0"},
                            },
                            modern_metadata=False,
                        )
                        if result.status is ProbeStatus.COMPLETE:
                            era = ProtocolEra.LEGACY
                    found_endpoint = True
                    break
                if found_endpoint:
                    break
                reconnects += 1
                if reconnects > self._max_reconnects:
                    result = ProbeResult(ProbeStatus.INCOMPLETE, "RECONNECT_LIMIT")
                    break
            except ValueError as error:
                result = ProbeResult(ProbeStatus.ERROR, str(error))
                break
            except (httpx.TimeoutException, httpx.TransportError):
                reconnects += 1
                if reconnects > self._max_reconnects:
                    result = ProbeResult(ProbeStatus.INCOMPLETE, "RECONNECT_LIMIT")
                    break
        return result, era
