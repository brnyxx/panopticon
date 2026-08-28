"""Pinned notification and session cleanup helpers for remote MCP."""

from __future__ import annotations

from typing import Protocol
from urllib.parse import urlsplit

import httpx

from .argument_schema import JsonValue
from .http_redirect import post_with_redirects
from .protocol import MODERN_PROTOCOL, ProbeResult, ProbeStatus, ProtocolEra
from .remote_security import Resolver, validate_url


class SessionClient(Protocol):
    client: httpx.AsyncClient
    endpoint: str
    timeout: float
    max_response: int
    _headers: dict[str, str]
    _resolver: Resolver | None
    _max_redirects: int
    era: ProtocolEra | None
    session_id: str | None
    close_reason: str | None


async def send_notification(
    client: SessionClient,
    method: str,
    params: dict[str, JsonValue] | None,
) -> ProbeResult:
    request_params = dict(params or {})
    if client.era is ProtocolEra.MODERN:
        request_params["_meta"] = {"client": "panopticon", "protocolVersion": MODERN_PROTOCOL}
    message: dict[str, JsonValue] = {
        "jsonrpc": "2.0",
        "method": method,
        "params": request_params,
    }
    headers = {**client._headers, "Content-Type": "application/json"}
    if client.session_id:
        headers["Mcp-Session-Id"] = client.session_id
    result = await post_with_redirects(
        client.client,
        client.endpoint,
        message,
        headers,
        timeout=client.timeout,
        resolver=client._resolver,
        max_redirects=client._max_redirects,
        max_response=client.max_response,
    )
    if isinstance(result, ProbeResult):
        return result
    response, client.endpoint, carried = result
    sensitive = {"authorization", "cookie", "mcp-session-id"}
    if any(name.casefold() in sensitive and name not in carried for name in headers):
        client._headers = {
            name: value
            for name, value in client._headers.items()
            if name.casefold() not in sensitive
        }
        client.session_id = None
    status = ProbeStatus.COMPLETE if response.status_code < 400 else ProbeStatus.ERROR
    return ProbeResult(status, "OK" if status is ProbeStatus.COMPLETE else "HTTP_ERROR")


async def close_session(client: SessionClient) -> None:
    if client.session_id is None:
        return
    try:
        decision = validate_url(client.endpoint, client._resolver)
        if not decision.allowed:
            client.close_reason = "SESSION_DELETE_BLOCKED"
            return
        logical = urlsplit(decision.url)
        transport = urlsplit(decision.transport_url)
        headers = {**client._headers, "Mcp-Session-Id": client.session_id}
        if (
            logical.hostname
            and logical.hostname.casefold() != (transport.hostname or "").casefold()
        ):
            headers["Host"] = logical.netloc
        response = await client.client.delete(
            decision.transport_url,
            headers=headers,
            timeout=client.timeout,
            extensions={"sni_hostname": logical.hostname} if logical.hostname else None,
        )
        if response.status_code in {301, 302, 303, 307, 308}:
            client.close_reason = "SESSION_DELETE_REDIRECTED"
        elif response.status_code >= 400:
            client.close_reason = "SESSION_DELETE_FAILED"
    except (httpx.TimeoutException, httpx.TransportError):
        client.close_reason = "SESSION_DELETE_FAILED"


__all__ = ["close_session", "send_notification"]
