"""Instrument and convert the exact remote MCP HTTP exchanges."""

from __future__ import annotations

import socket
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx

from panopticon.models.common import Host
from panopticon.models.event import Event, LeakEvent, NetEvent, PlaintextHttpEvent
from panopticon.probe.remote_security import Resolver
from panopticon.sandbox.decoy import DecoyManifest
from panopticon.sandbox.matcher import DecoyMatcher

from .watch_inventory import WatchTargetContext
from .watch_local_model import LocalSpan
from .watch_model import WatchOptions


class SystemResolver(Resolver):
    def resolve(self, host: str) -> tuple[str, ...]:
        values = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        return tuple(sorted({str(item[4][0]) for item in values}))


@dataclass(frozen=True, slots=True)
class Exchange:
    observed_at: datetime
    method: str
    url: str
    status: int
    request: bytes = field(repr=False)
    response: bytes = field(repr=False)


class ExchangeRecorder:
    def __init__(self) -> None:
        self._started: dict[int, tuple[datetime, bytes]] = {}
        self.exchanges: list[Exchange] = []

    async def request(self, request: httpx.Request) -> None:
        self._started[id(request)] = (datetime.now(UTC), request.content[:1_048_576])

    async def response(self, response: httpx.Response) -> None:
        await response.aread()
        started, request = self._started.pop(id(response.request), (datetime.now(UTC), b""))
        self.exchanges.append(
            Exchange(
                started,
                response.request.method,
                str(response.request.url),
                response.status_code,
                request,
                response.content[:4_194_304],
            )
        )


def request_headers(
    context: WatchTargetContext,
    options: WatchOptions,
    markers: tuple[str, ...],
) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    configured = context.raw_entry.raw.get("headers")
    values = configured if isinstance(configured, dict) else {}
    authorized = {name.casefold() for name in options.headers}
    headers: list[tuple[str, str]] = []
    secrets: list[str] = []
    for index, name in enumerate(context.target.headers_keys):
        raw = values.get(name)
        if name.casefold() in authorized and isinstance(raw, str):
            value = raw
            secrets.append(raw)
        else:
            value = markers[index % len(markers)]
        headers.append((name, value))
    return tuple(headers), tuple(secrets)


def _span_for(exchange: Exchange, spans: tuple[LocalSpan, ...]) -> str | None:
    candidates = [
        span for span in spans if span.started_at <= exchange.observed_at <= span.ended_at
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda span: span.ended_at - span.started_at).span_id


def events_by_span(
    exchanges: tuple[Exchange, ...],
    spans: tuple[LocalSpan, ...],
    manifest: DecoyManifest,
) -> dict[str, tuple[Event, ...]]:
    output: dict[str, list[Event]] = {}
    for exchange in exchanges:
        span_id = _span_for(exchange, spans)
        if span_id is None:
            continue
        parsed = urlsplit(exchange.url)
        host = (parsed.hostname or "unknown").casefold()
        events = output.setdefault(span_id, [])
        events.append(
            Event(
                NetEvent(
                    schema_version="1.0",
                    kind="net",
                    op="connect",
                    host=Host(host),
                    port=parsed.port or (443 if parsed.scheme == "https" else 80),
                    via="direct",
                    count=1,
                )
            )
        )
        request_matches = DecoyMatcher(manifest).match((exchange.request,)).matches
        if parsed.scheme == "http":
            events.append(
                Event(
                    PlaintextHttpEvent(
                        schema_version="1.0",
                        kind="plaintext_http",
                        op="request",
                        host=Host(host),
                        request_path=parsed.path or "/",
                        decoy_keys=tuple(sorted({item.key for item in request_matches})),
                        count=1,
                    )
                )
            )
        matches = DecoyMatcher(manifest).match((exchange.response,)).matches
        counts = Counter((item.key, "response") for item in matches)
        for (key, sink), count in sorted(counts.items()):
            events.append(
                Event(
                    LeakEvent(
                        schema_version="1.0",
                        kind="leak",
                        op="expose",
                        decoy_key=key,
                        sink=sink,
                        count=count,
                    )
                )
            )
    return {key: tuple(value) for key, value in output.items()}


__all__ = [
    "Exchange",
    "ExchangeRecorder",
    "SystemResolver",
    "events_by_span",
    "request_headers",
]
