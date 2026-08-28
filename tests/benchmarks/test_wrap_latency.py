"""Fixed-workload relay latency contract."""

from statistics import quantiles
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
    for _ in range(20):
        left, right = Writer(), Writer()
        started = perf_counter()
        await relay(Reader(workload), left, Reader(workload), right)
        samples.append((perf_counter() - started) * 1000)
    p95 = quantiles(samples, n=20, method="inclusive")[18]
    assert p95 <= 1.0
