"""Bounded subprocess stream handling."""

from __future__ import annotations

import asyncio

from .base import ExecResult, SandboxError, StreamResult


async def collect_stream(reader: asyncio.StreamReader, limit: int) -> StreamResult:
    """Read a stream with a hard memory bound, draining excess for process safety."""
    if limit < 0:
        raise ValueError("limit must be non-negative")
    data = bytearray()
    truncated = False
    while True:
        chunk = await reader.read(65536)
        if not chunk:
            break
        remaining = max(0, limit - len(data))
        data.extend(chunk[:remaining])
        if len(chunk) > remaining:
            truncated = True
    return StreamResult(bytes(data), truncated)


async def communicate(
    process: asyncio.subprocess.Process, stdin: bytes | None, limit: int
) -> ExecResult:
    """Collect both pipes concurrently, preventing pipe deadlocks."""
    if process.stdout is None or process.stderr is None:
        raise SandboxError("SUBPROCESS_PIPES_UNAVAILABLE")
    out_task = asyncio.create_task(collect_stream(process.stdout, limit))
    err_task = asyncio.create_task(collect_stream(process.stderr, limit))
    try:
        if stdin is not None and process.stdin is not None:
            process.stdin.write(stdin)
            await process.stdin.drain()
            process.stdin.close()
        await process.wait()
        stdout, stderr = await asyncio.gather(out_task, err_task)
        return ExecResult(process.returncode or 0, stdout, stderr)
    except asyncio.CancelledError:
        process.kill()
        await process.wait()
        out_task.cancel()
        err_task.cancel()
        await asyncio.gather(out_task, err_task, return_exceptions=True)
        raise
