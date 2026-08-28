from __future__ import annotations

import json

import httpx
import pytest

from panopticon.probe.http import StreamableHttpClient
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
