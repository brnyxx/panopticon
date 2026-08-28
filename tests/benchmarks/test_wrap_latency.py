"""Fixed-workload relay latency contract."""

import asyncio
from time import perf_counter

import pytest

from panopticon.wrap.relay import relay


class Reader:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    async def read(self, size: int = -1) -> bytes:
        payload, self.payload = self.payload, b""
        return payload


class Writer:
    def __init__(self) -> None:
        self.data = bytearray()

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


@pytest.mark.asyncio
async def test_wrap_relay_p95_added_latency_emits_value() -> None:
    workload = b'{"jsonrpc":"2.0","id":1}\n' * 64
    samples: list[float] = []

    async def direct_copy() -> None:
        async def one(reader: Reader, writer: Writer) -> None:
            writer.write(await reader.read())
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        await asyncio.gather(
            one(Reader(workload), Writer()),
            one(Reader(workload), Writer()),
        )

    for _ in range(5):
        await relay(Reader(workload), Writer(), Reader(workload), Writer())
        await direct_copy()
    for _ in range(30):
        left, right = Writer(), Writer()
        baseline_started = perf_counter()
        await direct_copy()
        baseline = perf_counter() - baseline_started
        started = perf_counter()
        await relay(Reader(workload), left, Reader(workload), right)
        added = max(0.0, perf_counter() - started - baseline)
        samples.append(added * 1000)
    p95 = sorted(samples)[28]
    assert p95 <= 1.0
