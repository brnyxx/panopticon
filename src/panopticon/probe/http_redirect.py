"""Redirect and legacy SSE helpers for the HTTP probe transport."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from urllib.parse import urljoin

import httpx

from .protocol import ProbeResult, ProbeStatus
from .remote_security import Resolver, same_origin, validate_url


async def post_with_redirects(
    client: httpx.AsyncClient,
    endpoint: str,
    message: Mapping[str, object],
    headers: dict[str, str],
    *,
    timeout: float,
    resolver: Resolver | None,
    max_redirects: int,
) -> tuple[httpx.Response, str, dict[str, str]] | ProbeResult:
    redirects = 0
    try:
        while True:
            response = await client.post(endpoint, json=message, headers=headers, timeout=timeout)
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response, endpoint, headers
            redirects += 1
            location = response.headers.get("location")
            if redirects > max_redirects or not location:
                return ProbeResult(ProbeStatus.INCOMPLETE, "REDIRECT_LIMIT")
            decision = validate_url(urljoin(endpoint, location), resolver)
            if not decision.allowed:
                return ProbeResult(ProbeStatus.UNSUPPORTED, "REDIRECT_" + decision.reason)
            if not same_origin(endpoint, decision.url):
                headers = {
                    name: value
                    for name, value in headers.items()
                    if name.casefold() not in {"authorization", "cookie", "mcp-session-id"}
                }
            endpoint = decision.transport_url
    except httpx.TimeoutException:
        return ProbeResult(ProbeStatus.INCOMPLETE, "TIMEOUT")
    except httpx.TransportError:
        return ProbeResult(ProbeStatus.INCOMPLETE, "TRANSPORT_ERROR")
    except asyncio.CancelledError:
        return ProbeResult(ProbeStatus.CANCELLED, "CANCELLED")


def response_payload(response: httpx.Response) -> object:
    media_type = response.headers.get("content-type", "").partition(";")[0].strip().casefold()
    if media_type == "text/event-stream":
        data = "\n".join(
            line.removeprefix("data:").lstrip()
            for line in response.text.splitlines()
            if line.startswith("data:")
        )
        return json.loads(data)
    return response.json()


def sse_endpoint(text: str) -> str | None:
    for line in text.splitlines():
        if line.casefold().startswith("data:"):
            value = line.partition(":")[2].strip()
            if value.startswith(("http://", "https://", "/")):
                return value
    return None
