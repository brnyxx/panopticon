"""Subprocess lifecycle and signal wiring for transparent stdio wrapping."""

from __future__ import annotations

import asyncio
import signal
import sys
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import replace
from typing import BinaryIO

from .model import AsyncReader, AsyncWriter, RelayResult
from .record import IsolatedRecorder
from .relay import relay


class ThreadReader:
    """Bounded adapter for a blocking binary input stream."""

    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream

    async def read(self, size: int = -1) -> bytes:
        return await asyncio.to_thread(self._stream.read, size)


class ThreadWriter:
    """Single-chunk backpressure adapter for a blocking binary output stream."""

    def __init__(self, stream: BinaryIO, *, close_stream: bool = False) -> None:
        self._stream = stream
        self._close_stream = close_stream
        self._pending: bytes | None = None

    def write(self, data: bytes) -> None:
        if self._pending is not None:
            raise RuntimeError("WRITE_WITHOUT_DRAIN")
        self._pending = data

    async def drain(self) -> None:
        pending, self._pending = self._pending, None
        if pending is None:
            return

        def write_and_flush() -> None:
            self._stream.write(pending)
            self._stream.flush()

        await asyncio.to_thread(write_and_flush)

    def close(self) -> None:
        if self._close_stream:
            self._stream.close()

    async def wait_closed(self) -> None:
        return None


async def _stop_process(process: asyncio.subprocess.Process, timeout: float) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout)
    except TimeoutError:
        process.kill()
        await process.wait()


async def run_command(
    command: Sequence[str],
    client_reader: AsyncReader,
    client_writer: AsyncWriter,
    *,
    recorder: IsolatedRecorder | None = None,
    server_id: str = "unknown",
    installation_id: str = "unknown",
    cleanup_timeout: float = 2.0,
) -> RelayResult:
    """Run one stdio child and preserve relay bytes, exit, half-close, and signals."""
    if not command or any(not argument for argument in command):
        raise ValueError("command must contain non-empty argv")
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=None,
    )
    if process.stdin is None or process.stdout is None:
        await _stop_process(process, cleanup_timeout)
        raise RuntimeError("CHILD_PIPE_UNAVAILABLE")
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    members: tuple[signal.Signals, ...] = (signal.SIGINT, signal.SIGTERM)
    sighup = getattr(signal, "SIGHUP", None)
    if isinstance(sighup, signal.Signals):
        members += (sighup,)
    for member in members:
        try:
            loop.add_signal_handler(member, process.send_signal, member)
            installed.append(member)
        except (NotImplementedError, RuntimeError):
            continue

    async def wait_child() -> int:
        code = await process.wait()
        stop_event.set()
        return code

    try:
        relay_result, exit_code = await asyncio.gather(
            relay(
                client_reader,
                process.stdin,
                process.stdout,
                client_writer,
                server_id=server_id,
                installation_id=installation_id,
                recorder=recorder,
                stop_event=stop_event,
            ),
            wait_child(),
        )
        return replace(relay_result, exit_code=exit_code)
    except asyncio.CancelledError:
        await _stop_process(process, cleanup_timeout)
        raise
    finally:
        for member in installed:
            with suppress(RuntimeError):
                loop.remove_signal_handler(member)


async def run_stdio_command(
    command: Sequence[str],
    *,
    recorder: IsolatedRecorder | None = None,
    server_id: str = "unknown",
    installation_id: str = "unknown",
) -> RelayResult:
    """Connect real process stdio to the cancellable event-loop pipe transports."""
    if sys.platform == "win32":
        return await run_command(
            command,
            ThreadReader(sys.stdin.buffer),
            ThreadWriter(sys.stdout.buffer),
            recorder=recorder,
            server_id=server_id,
            installation_id=installation_id,
        )
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    reader_protocol = asyncio.StreamReaderProtocol(reader)
    input_transport, _ = await loop.connect_read_pipe(
        lambda: reader_protocol,
        sys.stdin.buffer,
    )
    output_protocol = asyncio.streams.FlowControlMixin(loop=loop)
    output_transport, _ = await loop.connect_write_pipe(
        lambda: output_protocol,
        sys.stdout.buffer,
    )
    writer = asyncio.StreamWriter(output_transport, output_protocol, None, loop)
    try:
        return await run_command(
            command,
            reader,
            writer,
            recorder=recorder,
            server_id=server_id,
            installation_id=installation_id,
        )
    finally:
        input_transport.close()
        output_transport.close()


__all__ = ["ThreadReader", "ThreadWriter", "run_command", "run_stdio_command"]
