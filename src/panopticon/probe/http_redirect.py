"""Redirect and legacy SSE helpers for the HTTP probe transport."""

from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.parse import urljoin, urlsplit

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
    max_response: int,
) -> tuple[httpx.Response, str, dict[str, str]] | ProbeResult:
    redirects = 0
    try:
        while True:
            decision = validate_url(endpoint, resolver)
            if not decision.allowed:
                # Keep the transport's historical typed policy result; callers
                # treat all URL-policy failures as redirect-chain evidence.
                return ProbeResult(ProbeStatus.UNSUPPORTED, "REDIRECT_" + decision.reason)
            request_headers = dict(headers)
            logical_parts = urlsplit(decision.url)
            transport_parts = urlsplit(decision.transport_url)
            logical_host = logical_parts.hostname
            transport_host = transport_parts.hostname
            if (
                logical_host
                and transport_host
                and logical_host.casefold() != transport_host.casefold()
            ):
                request_headers["Host"] = logical_parts.netloc
            request = client.build_request(
                "POST",
                decision.transport_url,
                json=message,
                headers=request_headers,
                timeout=timeout,
                extensions={"sni_hostname": logical_host} if logical_host else None,
            )
            response = await client.send(request, stream=True)
            if response.extensions.get("pano_truncated") is True:
                await response.aclose()
                return ProbeResult(ProbeStatus.ERROR, "RESPONSE_TOO_LARGE")
            if not response.is_stream_consumed:
                captured = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(captured) + len(chunk) > max_response:
                        await response.aclose()
                        return ProbeResult(ProbeStatus.ERROR, "RESPONSE_TOO_LARGE")
                    captured.extend(chunk)
                response._content = bytes(captured)
            elif len(response.content) > max_response:
                return ProbeResult(ProbeStatus.ERROR, "RESPONSE_TOO_LARGE")
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response, decision.url, headers
            redirects += 1
            location = response.headers.get("location")
            if redirects > max_redirects or not location:
                return ProbeResult(ProbeStatus.INCOMPLETE, "REDIRECT_LIMIT")
            decision = validate_url(urljoin(decision.url, location), resolver)
            if not decision.allowed:
                return ProbeResult(ProbeStatus.UNSUPPORTED, "REDIRECT_" + decision.reason)
            if not same_origin(endpoint, decision.url):
                headers = {
                    name: value
                    for name, value in headers.items()
                    if name.casefold() not in {"authorization", "cookie", "mcp-session-id"}
                }
            endpoint = decision.url
    except httpx.TimeoutException:
        return ProbeResult(ProbeStatus.INCOMPLETE, "TIMEOUT")
    except httpx.TransportError:
        return ProbeResult(ProbeStatus.INCOMPLETE, "TRANSPORT_ERROR")


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


async def read_sse_events(
    response: httpx.Response,
    *,
    max_response: int,
    max_frame: int,
) -> tuple[tuple[str | None, str], ...]:
    """Read a bounded SSE stream, preserving event IDs for resume."""
    if max_response < 1 or max_frame < 1:
        raise ValueError("SSE bounds must be positive")
    total = 0
    frame = bytearray()
    events: list[tuple[str | None, str]] = []
    event_id: str | None = None
    data: list[str] = []
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_response:
            raise ValueError("RESPONSE_TOO_LARGE")
        frame.extend(chunk)
        if len(frame) > max_frame:
            raise ValueError("FRAME_TOO_LARGE")
        while b"\n" in frame:
            raw, _, rest = frame.partition(b"\n")
            frame = bytearray(rest)
            line = raw.rstrip(b"\r").decode("utf-8")
            if not line:
                if data:
                    events.append((event_id, "\n".join(data)))
                    data = []
                continue
            if line.startswith(":"):
                continue
            field, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if field == "id":
                event_id = value
            elif field == "data":
                data.append(value)
                if sum(len(item) for item in data) > max_frame:
                    raise ValueError("FRAME_TOO_LARGE")
    if frame:
        raise ValueError("MALFORMED_SSE")
    if data:
        events.append((event_id, "\n".join(data)))
    return tuple(events)
