"""Byte-preserving asynchronous stdio relay."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime

from .framing import Decoder, FrameError
from .model import AsyncReader, AsyncWriter, Clock, Coverage, RelayResult
from .record import Correlator, IsolatedRecorder, parse_and_correlate


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


async def relay(
    client_reader: AsyncReader,
    child_writer: AsyncWriter,
    child_reader: AsyncReader,
    client_writer: AsyncWriter,
    *,
    server_id: str = "unknown",
    installation_id: str = "unknown",
    recorder: IsolatedRecorder | None = None,
    clock: Clock | None = None,
    max_frame: int = 1_048_576,
    chunk_size: int = 65536,
    on_signal: Callable[[int], None] | None = None,
) -> RelayResult:
    """Relay both directions until EOF; parsing is advisory and never blocks bytes."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    clock = clock or SystemClock()
    recorder = recorder
    client_decoder, child_decoder = Decoder(max_frame), Decoder(max_frame)
    correlator = Correlator(server_id, installation_id)
    counts = [0, 0]
    parser_errors = 0
    recorder_errors = 0
    partial = False

    async def pump(reader: AsyncReader, writer: AsyncWriter, index: int, decoder: Decoder) -> None:
        nonlocal parser_errors, recorder_errors, partial
        while True:
            chunk = await reader.read(chunk_size)
            if not chunk:
                break
            counts[index] += len(chunk)
            writer.write(chunk)
            await writer.drain()
            try:
                records = parse_and_correlate(decoder, chunk, correlator, clock.now())
            except FrameError:
                parser_errors += 1
                partial = True
                continue
            if recorder is not None:
                for record in records:
                    if not recorder.record(record):
                        recorder_errors += 1
                        partial = True
        with suppress(OSError, RuntimeError):
            writer.close()
        wait_closed = getattr(writer, "wait_closed", None)
        if wait_closed is not None:
            await wait_closed()

    tasks = (
        asyncio.create_task(pump(client_reader, child_writer, 0, client_decoder)),
        asyncio.create_task(pump(child_reader, client_writer, 1, child_decoder)),
    )
    results = await asyncio.gather(*tasks, return_exceptions=True)
    exit_code: int | None = None
    for result in results:
        if isinstance(result, BaseException):
            partial = True
    return RelayResult(
        Coverage.PARTIAL if partial else Coverage.COMPLETE,
        counts[0],
        counts[1],
        exit_code,
        parser_errors,
        recorder_errors,
    )
