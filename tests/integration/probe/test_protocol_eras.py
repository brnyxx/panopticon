from __future__ import annotations

import asyncio
import json

import pytest

from panopticon.probe.client import McpClient
from panopticon.probe.protocol import ProbeStatus, ProtocolEra


def frame(payload: object) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode()
    return b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body


class InMemoryMcpServer:
    def __init__(self, *, legacy: bool = False) -> None:
        self.legacy = legacy
        self.responses: asyncio.Queue[bytes] = asyncio.Queue()
        self.requests: list[dict[str, object]] = []
        self.closed = False

    async def read(self, _size: int) -> bytes:
        return await self.responses.get()

    def write(self, data: bytes) -> None:
        payload = json.loads(data.split(b"\r\n\r\n", 1)[1])
        self.requests.append(payload)
        if "id" not in payload:
            return
        identifier = payload["id"]
        method = payload["method"]
        params = payload.get("params", {})
        if method == "initialize":
            version = params.get("protocolVersion")
            if self.legacy and version != "2024-11-05":
                response = {"id": identifier, "error": {"code": -32602}}
            else:
                response = {
                    "id": identifier,
                    "result": {
                        "protocolVersion": version,
                        "capabilities": {"tools": {}},
                    },
                }
        elif method == "tools/list":
            response = {
                "id": identifier,
                "result": {
                    "tools": [
                        {
                            "name": "echo",
                            "inputSchema": {
                                "type": "object",
                                "required": ["message"],
                                "properties": {"message": {"type": "string"}},
                            },
                        }
                    ]
                },
            }
        elif method == "tools/call":
            response = {"id": identifier, "result": {"content": params.get("arguments")}}
        else:
            response = {"id": identifier, "error": {"code": -32601}}
        self.responses.put_nowait(frame(response))

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_modern_and_legacy_list_and_call_tools() -> None:
    for legacy in (False, True):
        server = InMemoryMcpServer(legacy=legacy)
        client = McpClient(server, server)

        initialized = await client.initialize()
        listed = await client.list_paginated("tools/list")
        called = await client.request(
            "tools/call",
            {"name": "echo", "arguments": {"message": "hello"}},
        )

        assert initialized.status is ProbeStatus.COMPLETE
        assert client.era is (ProtocolEra.LEGACY if legacy else ProtocolEra.MODERN)
        assert listed.result == {
            "tools": [
                {
                    "name": "echo",
                    "inputSchema": {
                        "type": "object",
                        "required": ["message"],
                        "properties": {"message": {"type": "string"}},
                    },
                }
            ]
        }
        assert called.result == {"content": {"message": "hello"}}
        await client.close()


@pytest.mark.asyncio
async def test_version_retry_and_legacy_fallback() -> None:
    server = InMemoryMcpServer(legacy=True)
    client = McpClient(server, server)

    result = await client.initialize()

    versions = [
        request["params"]["protocolVersion"]
        for request in server.requests
        if request.get("method") == "initialize"
    ]
    assert result.reason_code == "LEGACY_FALLBACK"
    assert versions == ["2026-07-28", "2024-11-05"]
    assert client.era is ProtocolEra.LEGACY
    await client.close()
