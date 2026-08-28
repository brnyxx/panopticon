from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from panopticon.probe.http import StreamableHttpClient
from panopticon.probe.http_redirect import response_payload, sse_endpoint
from panopticon.probe.protocol import ProbeStatus, ProtocolEra


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

    assert result.status is ProbeStatus.COMPLETE
    assert seen[1].headers["authorization"] == "Bearer secret"
    assert seen[1].headers["cookie"] == "sid=1"
    assert "authorization" not in seen[2].headers
    assert "cookie" not in seen[2].headers
    assert "mcp-session-id" not in seen[2].headers


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
        result = await StreamableHttpClient("https://mcp.example/rpc", transport).request("x")
    assert result.reason_code == "CANCELLED"


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
