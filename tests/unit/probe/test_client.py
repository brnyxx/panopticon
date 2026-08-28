"""Event-driven protocol tests for the bounded MCP client."""

from __future__ import annotations

import asyncio
import json

import pytest

from panopticon.probe.client import McpClient, ProbeStatus, ProtocolEra


def frame(value: object) -> bytes:
    body = json.dumps(value, separators=(",", ":")).encode()
    return b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body


class Stream:
    def __init__(self) -> None:
        self.chunks: asyncio.Queue[bytes] = asyncio.Queue()
        self.writes: list[bytes] = []
        self.closed = False
        self.write_event = asyncio.Event()

    async def read(self, _n: int) -> bytes:
        return await self.chunks.get()

    def write(self, data: bytes) -> None:
        self.writes.append(data)
        self.write_event.set()

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def respond_to(self, index: int, result: object) -> None:
        await self.write_event.wait()
        request = json.loads(self.writes[index].split(b"\r\n\r\n", 1)[1])
        await self.chunks.put(frame({"jsonrpc": "2.0", "id": request["id"], "result": result}))
        self.write_event.clear()


@pytest.mark.asyncio
async def test_modern_initialize_records_metadata_and_sends_initialized() -> None:
    stream = Stream()
    client = McpClient(stream, stream)
    task = asyncio.create_task(client.initialize())
    await stream.respond_to(
        0,
        {
            "protocolVersion": "2026-07-28",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "srv", "version": "9"},
        },
    )
    result = await task
    assert result.status is ProbeStatus.COMPLETE
    assert client.era is ProtocolEra.MODERN
    assert client.server_info == {"name": "srv", "version": "9"}
    assert b"notifications/initialized" in stream.writes[-1]


@pytest.mark.asyncio
async def test_initialize_retries_legacy_version_after_modern_error() -> None:
    stream = Stream()
    client = McpClient(stream, stream)
    task = asyncio.create_task(client.initialize())
    await stream.write_event.wait()
    req = json.loads(stream.writes[0].split(b"\r\n\r\n", 1)[1])
    await stream.chunks.put(frame({"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32602}}))
    stream.write_event.clear()
    await stream.respond_to(1, {"capabilities": {}})
    result = await task
    assert result.status is ProbeStatus.COMPLETE
    assert client.era is ProtocolEra.LEGACY
    assert (
        json.loads(stream.writes[1].split(b"\r\n\r\n", 1)[1])["params"]["protocolVersion"]
        == "2024-11-05"
    )


@pytest.mark.asyncio
async def test_fragmented_content_length_and_out_of_order_ids() -> None:
    stream = Stream()
    client = McpClient(stream, stream)
    first = asyncio.create_task(client.request("a"))
    second = asyncio.create_task(client.request("b"))
    await stream.write_event.wait()
    ids = [json.loads(x.split(b"\r\n\r\n", 1)[1])["id"] for x in stream.writes]
    payload = frame({"id": ids[1], "result": "second"}) + frame({"id": ids[0], "result": "first"})
    for part in (payload[:3], payload[3:17], payload[17:]):
        await stream.chunks.put(part)
    assert (await first).result == "first"
    assert (await second).result == "second"


@pytest.mark.asyncio
async def test_malformed_batch_oversized_timeout_cancellation_and_early_exit() -> None:
    stream = Stream()
    client = McpClient(stream, stream, max_frame=256, timeout=0.01)
    malformed = asyncio.create_task(client.request("bad"))
    await stream.write_event.wait()
    req = json.loads(stream.writes[0].split(b"\r\n\r\n", 1)[1])
    await stream.chunks.put(frame([{"id": req["id"], "result": 1}]))
    assert (await malformed).reason_code == "MALFORMED_FRAME"
    assert (await client.notify("x", {"value": "x" * 1000})).reason_code == "REQUEST_TOO_LARGE"
    assert (await client.request("never")).reason_code == "TIMEOUT"
    stream.write_event.clear()
    pending = asyncio.create_task(client.request("cancel"))
    await stream.write_event.wait()
    pending.cancel()
    assert (await pending).status is ProbeStatus.CANCELLED
    early_stream = Stream()
    early = McpClient(early_stream, early_stream)
    early_task = asyncio.create_task(early.request("early"))
    await early_stream.write_event.wait()
    await early_stream.chunks.put(b"")
    assert (await early_task).reason_code == "EARLY_EXIT"
    await early.close()
    await client.close()
    assert stream.closed


@pytest.mark.asyncio
async def test_capability_gated_lists_and_duplicate_cursor() -> None:
    stream = Stream()
    client = McpClient(stream, stream)
    assert (await client.list_paginated("tools/list")).reason_code == "CAPABILITY_UNSUPPORTED"
    client.capabilities = {"tools": {}}
    task = asyncio.create_task(client.list_paginated("tools/list"))
    await stream.write_event.wait()
    req = json.loads(stream.writes[0].split(b"\r\n\r\n", 1)[1])
    await stream.chunks.put(
        frame({"id": req["id"], "result": {"tools": [{"name": "x"}], "nextCursor": "same"}})
    )
    stream.write_event.clear()
    await stream.respond_to(1, {"tools": [], "nextCursor": "same"})
    assert (await task).reason_code == "DUPLICATE_CURSOR"
    await client.close()
