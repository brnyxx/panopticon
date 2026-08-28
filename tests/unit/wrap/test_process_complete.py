import asyncio
import sys

import pytest

from panopticon.wrap.model import Coverage
from panopticon.wrap.process import ThreadReader, ThreadWriter, run_command


class Reader:
    def __init__(self, *chunks):
        self.chunks = list(chunks)

    async def read(self, size=-1):
        return self.chunks.pop(0) if self.chunks else b""


class Writer:
    def __init__(self):
        self.data = bytearray()
        self.closed = False

    def write(self, data):
        self.data.extend(data)

    async def drain(self):
        return None

    def close(self):
        self.closed = True

    async def wait_closed(self):
        return None


def child(code):
    return [sys.executable, "-c", code]


@pytest.mark.asyncio
async def test_run_command_relays_bytes_and_exit_code():
    client_out = Writer()
    result = await run_command(
        child(
            "import sys; "
            "data=sys.stdin.buffer.read(); "
            "sys.stdout.buffer.write(data.upper()); "
            "sys.stdout.flush()"
        ),
        Reader(b"hello", b""),
        client_out,
    )
    assert result.exit_code == 0
    assert result.coverage is Coverage.COMPLETE
    assert bytes(client_out.data) == b"HELLO"
    assert client_out.closed


@pytest.mark.asyncio
async def test_invalid_command_and_missing_pipe_errors():
    with pytest.raises(ValueError, match="non-empty"):
        await run_command((), Reader(), Writer())
    with pytest.raises(ValueError):
        await run_command((sys.executable, ""), Reader(), Writer())


@pytest.mark.asyncio
async def test_child_pipe_unavailable_is_stopped(monkeypatch):
    class Process:
        stdin = None
        stdout = None
        returncode = None

        def terminate(self):
            self.returncode = -15

        async def wait(self):
            return self.returncode

    process = Process()

    async def spawn(*args, **kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(RuntimeError, match="CHILD_PIPE_UNAVAILABLE"):
        await run_command(("tool",), Reader(), Writer())


@pytest.mark.asyncio
async def test_cancellation_stops_long_lived_child():
    started = asyncio.Event()

    class BlockingReader:
        async def read(self, size=-1):
            started.set()
            await asyncio.Future()

    task = asyncio.create_task(
        run_command(
            child("import time; time.sleep(30)"),
            BlockingReader(),
            Writer(),
            cleanup_timeout=0.05,
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_nonzero_child_exit_is_reported():
    result = await run_command(
        child("import sys; sys.stdin.buffer.read(); sys.exit(7)"),
        Reader(
            b"",
        ),
        Writer(),
    )
    assert result.exit_code == 7


@pytest.mark.asyncio
async def test_thread_stream_adapters_flush_and_close():
    import io

    stream = io.BytesIO()
    writer = ThreadWriter(stream, close_stream=True)
    writer.write(b"x")
    await writer.drain()
    assert stream.getvalue() == b"x"
    writer.close()
    reader = ThreadReader(io.BytesIO(b"abc"))
    assert await reader.read(2) == b"ab"
    await writer.wait_closed()
