from __future__ import annotations

import asyncio
import sys

import pytest

from panopticon.sandbox.streams import collect_stream, communicate


async def test_communicate_bounds_and_drains_both_streams() -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        (
            "import sys; "
            "sys.stdout.buffer.write(b'o' * 200000); "
            "sys.stderr.buffer.write(b'e' * 200000)"
        ),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    result = await communicate(process, None, 1024)

    assert result.returncode == 0
    assert result.stdout.data == b"o" * 1024
    assert result.stderr.data == b"e" * 1024
    assert result.stdout.truncated
    assert result.stderr.truncated


async def test_cancelling_communicate_reaps_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import sys; sys.stdin.buffer.read(1)",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    entered = asyncio.Event()

    async def observed_collect(reader: asyncio.StreamReader, limit: int):
        entered.set()
        return await collect_stream(reader, limit)

    monkeypatch.setattr("panopticon.sandbox.streams.collect_stream", observed_collect)
    task = asyncio.create_task(communicate(process, None, 1024))
    await asyncio.wait_for(entered.wait(), timeout=1)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.returncode is not None
