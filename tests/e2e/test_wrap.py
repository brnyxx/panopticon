import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from panopticon.store.contracts import PersistSuccess
from panopticon.store.repository import ArtifactRepository
from panopticon.wrap.framing import Decoder, encode
from panopticon.wrap.model import Coverage
from panopticon.wrap.persist import persist_record
from panopticon.wrap.process import run_command
from panopticon.wrap.record import Correlator, FirstSeen, IsolatedRecorder, parse_and_correlate
from panopticon.wrap.relay import relay
from panopticon.wrap.retention import lock_path, retention_paths, rotation_plan, utc_day


class Reader:
    def __init__(self, *chunks: bytes) -> None:
        self.chunks = list(chunks)

    async def read(self, size: int = -1) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""


class Writer:
    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False
        self.drains = 0

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        self.drains += 1

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class Sink:
    def __init__(self, fail: bool = False) -> None:
        self.records = []
        self.fail = fail

    def record(self, record) -> None:
        if self.fail:
            raise OSError("sink unavailable")
        self.records.append(record)


@pytest.mark.asyncio
async def test_clean_mcp_preserves_bytes_and_exit() -> None:
    client_bytes = b'{"jsonrpc":"2.0","id":1,"method":"tools/call"}\n'
    to_client = Writer()
    result = await asyncio.wait_for(
        run_command(
            (
                sys.executable,
                "-c",
                "import sys; data=sys.stdin.buffer.read(); "
                "sys.stdout.buffer.write(data); sys.exit(7)",
            ),
            Reader(client_bytes),
            to_client,
        ),
        timeout=2,
    )
    assert bytes(to_client.data) == client_bytes
    assert to_client.closed and to_client.drains == 1
    assert result.coverage is Coverage.COMPLETE
    assert result.bytes_client_to_child == len(client_bytes)
    assert result.bytes_child_to_client == len(client_bytes)
    assert result.exit_code == 7


@pytest.mark.asyncio
async def test_corrupt_frame_stops_recording_but_relay_continues() -> None:
    corrupt = b"{bad}\n"
    valid_request = encode(
        {"jsonrpc": "2.0", "id": "x", "method": "tools/call", "params": {"name": "ping"}}
    )
    valid_response = encode({"jsonrpc": "2.0", "id": "x", "result": {}})
    sink = Sink()
    to_child, to_client = Writer(), Writer()
    result = await asyncio.wait_for(
        relay(
            Reader(corrupt + valid_request),
            to_child,
            Reader(valid_response),
            to_client,
            recorder=IsolatedRecorder(sink),
        ),
        timeout=1,
    )
    assert bytes(to_child.data) == corrupt + valid_request
    assert bytes(to_client.data) == valid_response
    assert result.coverage is Coverage.PARTIAL
    assert result.parser_errors == 1
    assert result.bytes_client_to_child == len(corrupt + valid_request)
    assert sink.records == []


@pytest.mark.asyncio
async def test_recorder_failure_continues_relay_with_partial_coverage() -> None:
    request = encode({"id": 4, "method": "tools/call", "params": {"name": "inspect"}})
    response = encode({"id": 4, "result": {}})
    to_child, to_client = Writer(), Writer()
    result = await asyncio.wait_for(
        relay(
            Reader(request),
            to_child,
            Reader(response),
            to_client,
            recorder=IsolatedRecorder(Sink(fail=True)),
        ),
        timeout=1,
    )
    assert bytes(to_child.data) == request and bytes(to_client.data) == response
    assert result.coverage is Coverage.PARTIAL and result.recorder_errors == 1


def test_concurrent_out_of_order_ids_and_recorder_failure_are_partial(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    decoder, correlator = (
        Decoder(),
        Correlator(
            "local:fixture",
            "inst_0123456789abcdef",
        ),
    )
    batch = encode({"id": 1, "method": "tools/call", "params": {"name": "a"}})
    batch += encode({"id": 2, "method": "tools/call", "params": {"name": "b"}})
    batch += encode({"id": 2, "result": {}}) + encode({"id": 1, "result": {}})
    records = parse_and_correlate(decoder, batch, correlator, now)
    assert [r.span.request_id for r in records] == ["2", "1"]
    recorder = IsolatedRecorder(Sink(fail=True))
    assert not recorder.record(records[0])
    assert recorder.failures == 1
    persisted = persist_record(ArtifactRepository(tmp_path), records[0])
    assert isinstance(persisted, PersistSuccess)
    assert persisted.target.is_file()


def test_json_rpc_batches_correlate_out_of_order_responses() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    decoder, correlator = (
        Decoder(),
        Correlator(
            "local:fixture",
            "inst_0123456789abcdef",
        ),
    )
    requests = encode(
        [
            {"id": 1, "method": "tools/call", "params": {"name": "a"}},
            {"id": 2, "method": "tools/call", "params": {"name": "b"}},
        ]
    )
    responses = encode([{"id": 2, "result": {}}, {"id": 1, "result": {}}])
    records = parse_and_correlate(decoder, requests + responses, correlator, now)
    assert [(record.span.request_id, record.span.tool) for record in records] == [
        ("2", "b"),
        ("1", "a"),
    ]


def test_first_seen_alerts_and_utc_rotation_lock_retention() -> None:
    now = datetime(2026, 2, 1, 1, tzinfo=UTC)
    first = FirstSeen()
    alert = first.observe("i", "host:443/path", "/usr/bin/tool", now)
    assert alert and alert.host == "host" and alert.process == "tool"
    assert first.observe("i", "host:443/path", "/usr/bin/tool", now) is None
    plan = rotation_plan("/records", "srv", now)
    assert utc_day(now) == now.date() and plan.current.endswith("2026-02-01.ndjson")
    assert lock_path(plan.current) == plan.lock
    assert len(retention_paths("/records", "srv", now)) == 31


@pytest.mark.asyncio
async def test_relay_cancellation_closes_writers() -> None:
    class BlockingReader:
        def __init__(self) -> None:
            self.started = asyncio.Event()

        async def read(self, size: int = -1) -> bytes:
            self.started.set()
            await asyncio.Event().wait()
            return b""

    first = BlockingReader()
    second = BlockingReader()
    left, right = Writer(), Writer()
    task = asyncio.create_task(relay(first, left, second, right))
    await asyncio.wait_for(
        asyncio.gather(first.started.wait(), second.started.wait()),
        timeout=1,
    )
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1)
    assert task.done() and left.closed and right.closed
