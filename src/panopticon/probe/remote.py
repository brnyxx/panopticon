"""Transport-neutral Streamable HTTP and SSE observation client."""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from urllib.parse import urljoin

from .remote_events import RemoteEvent, leak_events, net_event, plaintext_event
from .remote_security import Resolver, validate_url, same_origin


class HttpResponse(Protocol):
    status: int
    headers: object
    body: bytes
    url: str


class HttpClient(Protocol):
    def request(self, method: str, url: str, headers: tuple[tuple[str, str], ...], body: bytes | None = None) -> HttpResponse: ...


class RemoteStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INCOMPLETE = "INCOMPLETE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class RemoteLimits:
    max_reconnects: int = 3
    max_redirects: int = 5
    max_request_bytes: int = 1_048_576
    max_response_bytes: int = 4_194_304
    max_url_length: int = 2048

@dataclass(frozen=True, slots=True)
class RemoteRequest:
    url: str
    method: str = "POST"
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes = b""
    decoys: tuple[tuple[str, str], ...] = ()
    allow_get: bool = True

@dataclass(frozen=True, slots=True)
class RemoteResult:
    status: RemoteStatus
    reason_code: str
    events: tuple[RemoteEvent, ...] = ()
    messages: tuple[dict[str, object], ...] = ()
    session_id: str | None = None


def _header(response: HttpResponse, key: str) -> str:
    headers = response.headers
    if hasattr(headers, "items"):
        for name, value in headers.items():  # type: ignore[attr-defined]
            if str(name).casefold() == key.casefold():
                return str(value)
    return ""


def _parse_sse(body: bytes, limit: int) -> tuple[dict[str, object], ...]:
    if len(body) > limit:
        return ()
    output: list[dict[str, object]] = []
    for chunk in body.decode("utf-8", "replace").split("\n\n"):
        data = "\n".join(line[5:].lstrip() for line in chunk.splitlines() if line.startswith("data:"))
        if data:
            try:
                value = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                output.append(value)
    return tuple(output)


class RemoteObserver:
    def __init__(self, client: HttpClient, resolver: Resolver | None = None, limits: RemoteLimits = RemoteLimits()) -> None:
        self.client, self.resolver, self.limits = client, resolver, limits

    def observe(self, request: RemoteRequest) -> RemoteResult:
        if len(request.url) > self.limits.max_url_length or len(request.body) > self.limits.max_request_bytes:
            return RemoteResult(RemoteStatus.INCOMPLETE, "LIMIT_EXCEEDED")
        decision = validate_url(request.url, self.resolver)
        if not decision.allowed:
            return RemoteResult(RemoteStatus.UNSUPPORTED, decision.reason)
        headers = request.headers
        events: list[RemoteEvent] = [net_event(decision.url)]
        if decision.url.startswith("http://"):
            events.append(plaintext_event(decision.url, headers, request.body))
        response = self.client.request(request.method, decision.url, headers, request.body)
        redirects = 0
        while response.status in {301, 302, 303, 307, 308}:
            redirects += 1
            location = _header(response, "location")
            if redirects > self.limits.max_redirects or not location:
                return RemoteResult(RemoteStatus.INCOMPLETE, "REDIRECT_LIMIT", tuple(events))
            target = validate_url(urljoin(decision.url, location), self.resolver, decision.url)
            if not target.allowed:
                return RemoteResult(RemoteStatus.UNSUPPORTED, "REDIRECT_" + target.reason, tuple(events))
            redirect_headers = headers if same_origin(decision.url, target.url) else tuple(
                (name, value) for name, value in headers
                if name.casefold() not in {"authorization", "cookie", "mcp-session-id"}
            )
            response = self.client.request("GET" if response.status == 303 else request.method, target.url, redirect_headers, None if response.status == 303 else request.body)
            decision = target
        if len(response.body) > self.limits.max_response_bytes:
            return RemoteResult(RemoteStatus.INCOMPLETE, "RESPONSE_LIMIT", tuple(events))
        session = _header(response, "mcp-session-id") or None
        media = _header(response, "content-type").casefold()
        messages = _parse_sse(response.body, self.limits.max_response_bytes) if "text/event-stream" in media else self._json(response.body)
        events.extend(leak_events(response.body, request.decoys, "response"))
        if response.status >= 400:
            return RemoteResult(RemoteStatus.INCOMPLETE, "HTTP_STATUS", tuple(events), messages, session)
        return RemoteResult(RemoteStatus.COMPLETE, "OK", tuple(events), messages, session)

    def resume(self, request: RemoteRequest, session_id: str, cursor: str | None = None) -> RemoteResult:
        extra = tuple((name, value) for name, value in request.headers if name.casefold() != "mcp-session-id")
        extra += (("Mcp-Session-Id", session_id),)
        if cursor:
            extra += (("Last-Event-ID", cursor),)
        return self.observe(RemoteRequest(request.url, "GET", extra, b"", request.decoys, True))

    def legacy(self, request: RemoteRequest) -> RemoteResult:
        result = self.observe(request)
        if result.status is RemoteStatus.INCOMPLETE and result.reason_code == "HTTP_STATUS":
            return self.observe(RemoteRequest(request.url, "GET", request.headers, b"", request.decoys, True))
        return result

    @staticmethod
    def _json(body: bytes) -> tuple[dict[str, object], ...]:
        try:
            value = json.loads(body)
        except json.JSONDecodeError:
            return ()
        if isinstance(value, dict):
            return (value,)
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return tuple(value)
        return ()


__all__ = ["HttpResponse", "HttpClient", "RemoteStatus", "RemoteLimits", "RemoteRequest", "RemoteResult", "RemoteObserver"]
