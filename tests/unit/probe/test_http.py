from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from panopticon.probe.http import StreamableHttpClient
from panopticon.probe.http_redirect import response_payload, sse_endpoint
from panopticon.probe.protocol import ProbeStatus, ProtocolEra


class _Stream(httpx.AsyncByteStream):
    def __init__(self, *chunks: bytes) -> None:
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_modern_http_initialize_metadata_session_and_era_cache() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content) if request.content else {}
        if request.method == "DELETE":
            return httpx.Response(200)
        if "id" not in payload:
            return httpx.Response(202)
        return httpx.Response(
            200,
            headers={"Mcp-Session-Id": "session-1"},
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "protocolVersion": "2026-07-28",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "server"},
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = StreamableHttpClient("https://mcp.example/rpc", transport)
        result = await client.initialize()
        await client.close()

    initialize = json.loads(requests[0].content)
    assert result.status is ProbeStatus.COMPLETE
    assert client.era is ProtocolEra.MODERN
    assert client.era_cache.get(client.endpoint) is ProtocolEra.MODERN
    assert initialize["params"]["_meta"]["protocolVersion"] == "2026-07-28"
    assert requests[1].headers["Mcp-Session-Id"] == "session-1"
    assert requests[-1].method == "DELETE"


@pytest.mark.asyncio
async def test_http_version_retry_falls_back_to_legacy() -> None:
    versions: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if "id" not in payload:
            return httpx.Response(202)
        version = payload["params"]["protocolVersion"]
        versions.append(version)
        if version == "2026-07-28":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": payload["id"], "error": {"code": -32602}},
            )
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": {"capabilities": {}}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = StreamableHttpClient("https://mcp.example/rpc", transport)
        result = await client.initialize()

    assert result.reason_code == "LEGACY_FALLBACK"
    assert client.era is ProtocolEra.LEGACY
    assert versions == ["2026-07-28", "2024-11-05"]


@pytest.mark.asyncio
async def test_sse_response_limits_malformed_and_server_crash_are_typed() -> None:
    def sse_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        data = json.dumps({"jsonrpc": "2.0", "id": payload["id"], "result": {"tools": []}})
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, text=f"data: {data}\n\n"
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(sse_handler)) as transport:
        sse = StreamableHttpClient("https://mcp.example/rpc", transport)
        assert (await sse.request("tools/list")).status is ProbeStatus.COMPLETE

    def oversized_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 65)

    async with httpx.AsyncClient(transport=httpx.MockTransport(oversized_handler)) as transport:
        limited = StreamableHttpClient("https://mcp.example/rpc", transport, max_response=64)
        assert (await limited.request("x")).reason_code == "RESPONSE_TOO_LARGE"

    def crash_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(crash_handler)) as transport:
        crashed = StreamableHttpClient("https://mcp.example/rpc", transport)
        assert (await crashed.request("x")).reason_code == "SERVER_CRASH"


@pytest.mark.asyncio
async def test_http_timeout_is_incomplete() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("bounded", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = StreamableHttpClient("https://mcp.example/rpc", transport)
        result = await client.request("slow")

    assert result.status is ProbeStatus.INCOMPLETE
    assert result.reason_code == "TIMEOUT"


@pytest.mark.asyncio
async def test_redirects_preserve_same_origin_and_strip_cross_origin_credentials() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(307, headers={"location": "/same"}, request=request)
        if len(seen) == 2:
            return httpx.Response(
                307, headers={"location": "https://other.example/rpc"}, request=request
            )
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = StreamableHttpClient(
            "https://mcp.example/rpc",
            transport,
            headers=(("Authorization", "Bearer secret"), ("Cookie", "sid=1")),
        )
        client.session_id = "session-1"
        result = await client.request("tools/list")
        notified = await client.notify("notifications/initialized")

    assert result.status is ProbeStatus.COMPLETE
    assert notified.status is ProbeStatus.COMPLETE
    assert seen[1].headers["authorization"] == "Bearer secret"
    assert seen[1].headers["cookie"] == "sid=1"
    assert "authorization" not in seen[2].headers
    assert "cookie" not in seen[2].headers
    assert "mcp-session-id" not in seen[2].headers
    assert "authorization" not in seen[3].headers
    assert "cookie" not in seen[3].headers
    assert "mcp-session-id" not in seen[3].headers
    assert client.session_id is None


@pytest.mark.asyncio
async def test_redirect_limit_and_missing_location_are_bounded() -> None:
    async def looping(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/again"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(looping)) as transport:
        limited = StreamableHttpClient("https://mcp.example/rpc", transport, max_redirects=1)
        result = await limited.request("x")
    assert result.reason_code == "REDIRECT_LIMIT"

    async def missing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(missing)) as transport:
        result = await StreamableHttpClient("https://mcp.example/rpc", transport).request("x")
    assert result.reason_code == "REDIRECT_LIMIT"


@pytest.mark.asyncio
async def test_redirect_blocked_resolver_and_transport_cancel_paths() -> None:
    class BlockedResolver:
        def resolve(self, _host: str) -> tuple[str, ...]:
            return ("10.0.0.1",)

    async def redirect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302, headers={"location": "https://other.example/rpc"}, request=request
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(redirect)) as transport:
        blocked = StreamableHttpClient(
            "https://mcp.example/rpc", transport, resolver=BlockedResolver()
        )
        result = await blocked.request("x")
    assert result.status is ProbeStatus.UNSUPPORTED
    assert result.reason_code == "REDIRECT_ADDRESS_BLOCKED"

    async def transport_error(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport_error)) as transport:
        result = await StreamableHttpClient("https://mcp.example/rpc", transport).request("x")
    assert result.reason_code == "TRANSPORT_ERROR"

    async def cancelled(_request: httpx.Request) -> httpx.Response:
        raise asyncio.CancelledError

    async with httpx.AsyncClient(transport=httpx.MockTransport(cancelled)) as transport:
        with pytest.raises(asyncio.CancelledError):
            await StreamableHttpClient("https://mcp.example/rpc", transport).request("x")


def test_sse_response_payload_and_endpoint_parsing() -> None:
    payload = {"jsonrpc": "2.0", "id": 7, "result": {"ok": True}}
    response = httpx.Response(
        200,
        headers={"content-type": "text/event-stream; charset=utf-8"},
        text=f"event: message\ndata: {json.dumps(payload)}\n\n",
    )
    assert response_payload(response) == payload
    assert sse_endpoint("retry: 1\ndata: /messages\n\n") == "/messages"
    assert sse_endpoint("data: https://mcp.example/messages\n") == "https://mcp.example/messages"
    assert sse_endpoint("event: endpoint\ndata: not-a-url\n") is None


@pytest.mark.asyncio
async def test_legacy_sse_endpoint_redirects_initialize_over_mock_transport() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text="event: endpoint\ndata: /messages\n\n",
                request=request,
            )
        payload = json.loads(request.content)
        if len(requests) == 1:
            return httpx.Response(400, request=request)
        if payload.get("method") == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": payload["id"], "result": {"capabilities": {}}},
                request=request,
            )
        return httpx.Response(202, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = StreamableHttpClient("https://mcp.example/rpc", transport)
        result = await client.initialize()

    assert result.status is ProbeStatus.COMPLETE
    assert client.endpoint == "https://mcp.example/messages"
    assert [request.method for request in requests[:3]] == ["POST", "GET", "POST"]


@pytest.mark.asyncio
async def test_sse_discovery_preserves_event_cursor_and_last_event_id_on_reconnect() -> None:
    requests: list[httpx.Request] = []
    streams: list[_Stream] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            payload = json.loads(request.content)
            if len(requests) == 1:
                return httpx.Response(400, request=request)
            if "id" not in payload:
                return httpx.Response(202, request=request)
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": payload["id"], "result": {"capabilities": {}}},
                request=request,
            )
        stream = (
            _Stream(
                b"id: cursor-1\n",
                b"data: not-an-endpoint\n\n",
            )
            if len(streams) == 0
            else _Stream(
                b"id: cursor-2\n",
                b"event: endpoint\n",
                b"data: /messages\n\n",
            )
        )
        streams.append(stream)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=stream,
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = StreamableHttpClient("https://mcp.example/rpc", transport, max_reconnects=2)
        result = await client.initialize()

    assert result.reason_code == "LEGACY_FALLBACK"
    assert client.endpoint == "https://mcp.example/messages"
    assert client.last_event_id == "cursor-2"
    assert requests[1].method == "GET"
    assert requests[2].headers["Last-Event-ID"] == "cursor-1"
    assert streams[0].closed and streams[1].closed


@pytest.mark.asyncio
async def test_sse_reconnect_limit_and_stream_bounds_are_typed() -> None:
    async def no_endpoint(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            payload = json.loads(request.content)
            return httpx.Response(
                400 if payload["method"] == "initialize" else 202, request=request
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_Stream(b"data: still-not-an-endpoint\n\n"),
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(no_endpoint)) as transport:
        client = StreamableHttpClient("https://mcp.example/rpc", transport, max_reconnects=1)
        result = await client.initialize()
    assert result.reason_code == "RECONNECT_LIMIT"

    async def huge(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_Stream(b"data: " + b"x" * 32 + b"\n\n"),
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(huge)) as transport:
        client = StreamableHttpClient("https://mcp.example/rpc", transport, max_response=16)
        result = await client.request("x")
    assert result.reason_code == "RESPONSE_TOO_LARGE"


@pytest.mark.asyncio
async def test_sse_malformed_utf8_frame_and_cursor_limits_are_typed() -> None:
    async def malformed(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_Stream(b"data: \xff\n\n"),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(malformed)) as transport:
        result = await StreamableHttpClient("https://mcp.example/rpc", transport).request("x")
    assert result.reason_code == "MALFORMED_RESPONSE"

    async def long_cursor(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_Stream(b"id: " + b"x" * 257 + b"\ndata: /messages\n\n"),
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(long_cursor)) as transport:
        client = StreamableHttpClient("https://mcp.example/rpc", transport)
        result = await client.request("x")
    assert result.reason_code == "CURSOR_TOO_LARGE"


@pytest.mark.asyncio
async def test_sse_stream_frame_errors_close_stream_and_bound_retries() -> None:
    streams: list[_Stream] = []

    async def malformed(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(400, request=request)
        stream = _Stream(b"data: /messages")  # no terminating newline
        streams.append(stream)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=stream,
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(malformed)) as transport:
        client = StreamableHttpClient("https://mcp.example/rpc", transport, max_reconnects=0)
        result = await client.initialize()
    assert result.reason_code == "MALFORMED_SSE"
    assert streams[0].closed

    async def oversized(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(400, request=request)
        stream = _Stream(b"x" * 20)
        streams.append(stream)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=stream,
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(oversized)) as transport:
        client = StreamableHttpClient("https://mcp.example/rpc", transport, max_response=16)
        result = await client.initialize()
    assert result.reason_code == "RESPONSE_TOO_LARGE"
    assert streams[-1].closed


@pytest.mark.asyncio
async def test_sse_stream_timeout_and_transport_errors_use_reconnect_limit() -> None:
    calls = 0

    async def failing(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.method == "POST":
            return httpx.Response(400, request=request)
        calls += 1
        raise httpx.ReadTimeout("stream timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(failing)) as transport:
        client = StreamableHttpClient("https://mcp.example/rpc", transport, max_reconnects=1)
        result = await client.initialize()
    assert result.reason_code == "RECONNECT_LIMIT"
    assert calls == 2

    async def transport_error(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(400, request=request)
        raise httpx.ConnectError("stream down", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport_error)) as transport:
        client = StreamableHttpClient("https://mcp.example/rpc", transport, max_reconnects=0)
        result = await client.initialize()
    assert result.reason_code == "RECONNECT_LIMIT"
