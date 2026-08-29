"""Event-driven protocol tests for the bounded MCP client."""

from __future__ import annotations

import asyncio
import json

import pytest

from panopticon.probe.client import McpClient, ProbeStatus, ProtocolEra
from panopticon.probe.protocol import FrameDecoder, FrameError, encode_message


def frame(value: object) -> bytes:
    body = json.dumps(value, separators=(",", ":")).encode()
    return b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body


def sent(value: bytes) -> dict[str, object]:
    decoded = json.loads(value)
    assert isinstance(decoded, dict)
    return decoded


def test_jsonl_frame_decoder_handles_fragmented_multiple_and_blank_lines() -> None:
    decoder = FrameDecoder()
    payload = b'\n{"id":1,"result":"one"}\r\n{"id":2,"result":"two"}\n'
    assert decoder.feed(payload[:10]) == ()
    assert decoder.feed(payload[10:20]) == ()
    assert decoder.feed(payload[20:]) == (
        {"id": 1, "result": "one"},
        {"id": 2, "result": "two"},
    )


def test_frame_decoder_accepts_legacy_content_length_and_truncation() -> None:
    decoder = FrameDecoder()
    body = b'{"id":7,"result":"ok"}'
    framed = b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
    assert decoder.feed(framed[:-2]) == ()
    assert decoder.feed(framed[-2:]) == ({"id": 7, "result": "ok"},)


def test_frame_decoder_rejects_malformed_json_and_batches() -> None:
    with pytest.raises(FrameError, match="MALFORMED_FRAME"):
        FrameDecoder().feed(b'{"id":1\n')
    with pytest.raises(FrameError, match="BATCH_UNSUPPORTED"):
        FrameDecoder().feed(b'[{"id":1}]\n')


def test_frame_decoder_rejects_oversized_response_and_invalid_max_frame() -> None:
    with pytest.raises(ValueError, match="positive"):
        FrameDecoder(0)
    with pytest.raises(FrameError, match="RESPONSE_TOO_LARGE"):
        FrameDecoder(max_frame=8).feed(b'{"value":"too-large"}\n')
    with pytest.raises(FrameError, match="RESPONSE_TOO_LARGE"):
        FrameDecoder(max_frame=8).feed(b"Content-Length: 9\r\n\r\n123456789")
    with pytest.raises(FrameError, match="RESPONSE_TOO_LARGE"):
        FrameDecoder(max_frame=8).feed(b"x" * 17)


def test_frame_decoder_rejects_malformed_content_length_headers() -> None:
    malformed = (
        b"Content-Length: nope\r\n\r\n{}",
        b"Content-Length: -1\r\n\r\n{}",
        b"Content-Length: 2\r\nX\r\n\r\n{}",
        b"Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}",
    )
    for payload in malformed:
        with pytest.raises(FrameError, match="MALFORMED_HEADER"):
            FrameDecoder().feed(payload)


def test_encode_message_emits_jsonl_and_rejects_oversized_requests() -> None:
    encoded = encode_message({"jsonrpc": "2.0", "method": "ping"})
    assert encoded.endswith(b"\n")
    assert b"Content-Length" not in encoded
    assert json.loads(encoded) == {"jsonrpc": "2.0", "method": "ping"}
    with pytest.raises(FrameError, match="REQUEST_TOO_LARGE"):
        encode_message({"value": "x" * 20}, max_frame=8)


class Stream:
    def __init__(self) -> None:
        self.chunks: asyncio.Queue[bytes] = asyncio.Queue()
        self.writes: list[bytes] = []
        self.closed = False
        self.write_event = asyncio.Event()
        self.write_queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def read(self, _n: int) -> bytes:
        return await self.chunks.get()

    def write(self, data: bytes) -> None:
        self.writes.append(data)
        self.write_queue.put_nowait(data)
        self.write_event.set()

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def respond_to(self, index: int, result: object) -> None:
        await self.write_event.wait()
        request = sent(self.writes[index])
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
    initialize = sent(stream.writes[0])
    assert initialize["params"]["_meta"]["protocolVersion"] == "2026-07-28"
    assert b"notifications/initialized" in stream.writes[-1]


@pytest.mark.asyncio
async def test_initialize_retries_legacy_version_after_modern_error() -> None:
    stream = Stream()
    client = McpClient(stream, stream)
    task = asyncio.create_task(client.initialize())
    await stream.write_event.wait()
    req = sent(stream.writes[0])
    await stream.chunks.put(frame({"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32602}}))
    stream.write_event.clear()
    await stream.respond_to(
        1,
        {"protocolVersion": "2024-11-05", "capabilities": {}},
    )
    result = await task
    assert result.status is ProbeStatus.COMPLETE
    assert result.reason_code == "LEGACY_FALLBACK"
    assert client.era is ProtocolEra.LEGACY
    assert sent(stream.writes[1])["params"]["protocolVersion"] == "2024-11-05"
    assert "_meta" not in sent(stream.writes[1])["params"]


@pytest.mark.asyncio
async def test_advertised_server_discovery_is_capability_gated() -> None:
    stream = Stream()
    client = McpClient(stream, stream)
    task = asyncio.create_task(client.initialize())
    initialize = await stream.write_queue.get()
    initialize_id = sent(initialize)["id"]
    await stream.chunks.put(
        frame(
            {
                "id": initialize_id,
                "result": {
                    "protocolVersion": "2026-07-28",
                    "capabilities": {"serverDiscovery": {}},
                },
            }
        )
    )
    initialized_notification = await stream.write_queue.get()
    discover_request = await stream.write_queue.get()
    assert b"notifications/initialized" in initialized_notification
    discover_payload = sent(discover_request)
    assert discover_payload["method"] == "server/discover"
    await stream.chunks.put(frame({"id": discover_payload["id"], "result": {"transports": []}}))

    assert (await task).status is ProbeStatus.COMPLETE


@pytest.mark.asyncio
async def test_fragmented_content_length_and_out_of_order_ids() -> None:
    stream = Stream()
    client = McpClient(stream, stream)
    first = asyncio.create_task(client.request("a"))
    second = asyncio.create_task(client.request("b"))
    await stream.write_event.wait()
    ids = [sent(x)["id"] for x in stream.writes]
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
    req = sent(stream.writes[0])
    await stream.chunks.put(frame([{"id": req["id"], "result": 1}]))
    assert (await malformed).reason_code == "BATCH_UNSUPPORTED"
    assert (await client.request("after-batch")).reason_code == "STREAM_DESYNCHRONIZED"
    await client.close()

    oversized_stream = Stream()
    oversized = McpClient(oversized_stream, oversized_stream, max_frame=256)
    assert (await oversized.notify("x", {"value": "x" * 1000})).reason_code == ("REQUEST_TOO_LARGE")
    await oversized.close()

    timeout_stream = Stream()
    timeout_client = McpClient(timeout_stream, timeout_stream, timeout=0.01)
    assert (await timeout_client.request("never")).reason_code == "TIMEOUT"
    assert timeout_stream.closed
    assert (await timeout_client.request("after-timeout")).reason_code == ("STREAM_DESYNCHRONIZED")

    cancel_stream = Stream()
    cancel_client = McpClient(cancel_stream, cancel_stream)
    pending = asyncio.create_task(cancel_client.request("cancel"))
    await cancel_stream.write_event.wait()
    pending.cancel()
    assert (await pending).status is ProbeStatus.CANCELLED
    assert b"notifications/cancelled" in cancel_stream.writes[-1]
    await cancel_client.close()

    early_stream = Stream()
    early = McpClient(early_stream, early_stream)
    early_task = asyncio.create_task(early.request("early"))
    await early_stream.write_event.wait()
    await early_stream.chunks.put(b"")
    assert (await early_task).reason_code == "EARLY_EXIT"
    await early.close()


@pytest.mark.asyncio
async def test_capability_gated_lists_and_duplicate_cursor() -> None:
    stream = Stream()
    client = McpClient(stream, stream)
    assert (await client.list_paginated("tools/list")).reason_code == "CAPABILITY_UNSUPPORTED"
    client.capabilities = {"tools": {}}
    task = asyncio.create_task(client.list_paginated("tools/list"))
    await stream.write_event.wait()
    req = sent(stream.writes[0])
    await stream.chunks.put(
        frame({"id": req["id"], "result": {"tools": [{"name": "x"}], "nextCursor": "same"}})
    )
    stream.write_event.clear()
    await stream.respond_to(1, {"tools": [], "nextCursor": "same"})
    assert (await task).reason_code == "DUPLICATE_CURSOR"
    await client.close()
