"""Protocol-valid HTTPS MCP checks using an injected transport."""

from __future__ import annotations

import socket
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import httpx
from pydantic import JsonValue, TypeAdapter, ValidationError

from panopticon.probe.remote_security import validate_url

_JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
_CREDENTIAL_KEYS = {"access_token", "api_key", "apikey", "key", "secret", "token"}


class HttpTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None = None,
    ) -> tuple[int, Mapping[str, str], bytes]: ...


class _SocketResolver:
    def resolve(self, host: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    str(item[4][0])
                    for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
                }
            )
        )


class HttpxTransport:
    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None = None,
    ) -> tuple[int, Mapping[str, str], bytes]:
        decision = validate_url(url, _SocketResolver())
        if not decision.allowed:
            raise ValueError(decision.reason)
        try:
            with httpx.Client(
                follow_redirects=False,
                timeout=5.0,
                trust_env=False,
            ) as client:
                response = client.request(
                    method, decision.transport_url, headers=headers, content=body
                )
        except httpx.HTTPError as error:
            raise RuntimeError("HTTPS_REQUEST_FAILED") from error
        return response.status_code, response.headers, response.content


@dataclass(frozen=True, slots=True)
class HttpsCheck:
    ok: bool
    url: str
    code: str


def https_url(url: str) -> str:
    parts = urlsplit(url)
    if (
        parts.scheme != "http"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
    ):
        raise ValueError("INVALID_HTTP_URL")
    if any(key.casefold() in _CREDENTIAL_KEYS for key, _value in parse_qsl(parts.query)):
        raise ValueError("CREDENTIAL_QUERY_UNSUPPORTED")
    host = parts.hostname.casefold()
    if ":" in host:
        host = f"[{host}]"
    netloc = host if parts.port in (None, 443) else f"{host}:{parts.port}"
    return urlunsplit(("https", netloc, parts.path or "/", parts.query, ""))


def _valid_initialize(payload: bytes) -> bool:
    if len(payload) > 1_048_576:
        return False
    try:
        value = _JSON.validate_json(payload)
    except ValidationError:
        return False
    if not isinstance(value, dict):
        return False
    result = value.get("result")
    return (
        value.get("jsonrpc") == "2.0"
        and value.get("id") == 1
        and isinstance(result, dict)
        and isinstance(result.get("protocolVersion"), str)
    )


def check_initialize(url: str, transport: HttpTransport) -> HttpsCheck:
    """POST MCP initialize, never HEAD; only a matching protocol response passes."""
    target = https_url(url)
    body = (
        b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":'
        b'{"protocolVersion":"2026-07-28","capabilities":{}}}'
    )
    try:
        status, _headers, payload = transport.request(
            "POST",
            target,
            {"content-type": "application/json", "accept": "application/json"},
            body,
        )
    except (OSError, RuntimeError, ValueError):
        return HttpsCheck(False, target, "HTTPS_UNAVAILABLE")
    if not 200 <= status < 300:
        return HttpsCheck(False, target, "MCP_INITIALIZE_FAILED")
    if not _valid_initialize(payload):
        return HttpsCheck(False, target, "MCP_PROTOCOL_INVALID")
    return HttpsCheck(True, target, "MCP_INITIALIZE_OK")


__all__ = ["HttpTransport", "HttpsCheck", "HttpxTransport", "check_initialize", "https_url"]
