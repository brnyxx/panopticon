from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from panopticon.registry.cache import CacheEnvelope, CacheLoad, CacheLoadStatus
from panopticon.registry.client import RegistryFetch
from panopticon.registry.history import SnapshotSeries, append_snapshot
from panopticon.registry.model import HistoryReason, HistoryStatus, NormalizedHistory
from panopticon.registry.provider import RegistryProvider

NOW = datetime(2025, 1, 1, tzinfo=UTC)


def _server(ecosystem: str = "npm") -> SimpleNamespace:
    package = SimpleNamespace(
        ecosystem=SimpleNamespace(value=ecosystem), name="pkg", pinned="1.0.0", resolved=None
    )
    return SimpleNamespace(
        package=package,
        source=SimpleNamespace(kind=SimpleNamespace(value="registry"), url=None),
        name="fixture",
    )


def _history() -> NormalizedHistory:
    return NormalizedHistory(
        status=HistoryStatus.AVAILABLE,
        reason_code=HistoryReason.OK,
        ecosystem="npm",
        name="pkg",
        requested_spec="1.0.0",
        resolved_version="1.0.0",
        registry_fetched_at=NOW,
        registry_fresh=True,
    )


class Clock:
    def now(self) -> datetime:
        return NOW


class Cache:
    def __init__(self, loaded: CacheLoad) -> None:
        self.loaded = loaded
        self.persisted: CacheEnvelope | None = None

    def load(self, lookup, *, now=None) -> CacheLoad:
        return self.loaded

    def persist(self, lookup, envelope: CacheEnvelope) -> CacheLoad:
        self.persisted = envelope
        return CacheLoad(CacheLoadStatus.HIT, envelope)


class Client:
    def __init__(self, failure: bool = False) -> None:
        self.clock = Clock()
        self.calls = 0
        self.failure = failure

    async def fetch(
        self,
        lookup,
        *,
        snapshots: SnapshotSeries | None = None,
        etags: tuple[tuple[str, str], ...] = (),
    ) -> RegistryFetch:
        del etags
        self.calls += 1
        assert snapshots is not None
        if self.failure:
            history = NormalizedHistory(
                status=HistoryStatus.UNKNOWN,
                reason_code=HistoryReason.TIMEOUT,
                ecosystem="npm",
                name="pkg",
                requested_spec="1.0.0",
            )
            return RegistryFetch(history, snapshots, True, "TIMEOUT")
        updated = append_snapshot(snapshots, _history(), observed_at=NOW)
        return RegistryFetch(_history(), updated, True, "OK")


@pytest.mark.asyncio
async def test_offline_cache_miss_never_calls_http() -> None:
    cache = Cache(CacheLoad(CacheLoadStatus.MISS, reason_code="CACHE_MISS"))
    client = Client()

    result = await RegistryProvider(cache, client).lookup(_server(), offline=True)

    assert client.calls == 0
    assert result.history is not None
    assert result.history.status is HistoryStatus.UNKNOWN
    assert result.reason_code is HistoryReason.OFFLINE


@pytest.mark.asyncio
async def test_online_miss_fetches_and_persists_normalized_series() -> None:
    cache = Cache(CacheLoad(CacheLoadStatus.MISS, reason_code="CACHE_MISS"))
    client = Client()

    result = await RegistryProvider(cache, client).lookup(_server())

    assert client.calls == 1
    assert result.status is HistoryStatus.AVAILABLE
    assert cache.persisted is not None
    assert cache.persisted.snapshots == result.series


@pytest.mark.asyncio
async def test_fresh_cache_avoids_http() -> None:
    series = append_snapshot(SnapshotSeries(), _history(), observed_at=NOW)
    envelope = CacheEnvelope(ecosystem="npm", name="pkg", snapshots=series, fetched_at=NOW)
    cache = Cache(CacheLoad(CacheLoadStatus.HIT, envelope))
    client = Client()

    result = await RegistryProvider(cache, client).lookup(_server())

    assert client.calls == 0
    assert result.status is HistoryStatus.AVAILABLE


@pytest.mark.asyncio
async def test_online_failure_does_not_persist_unknown_history() -> None:
    cache = Cache(CacheLoad(CacheLoadStatus.MISS, reason_code="CACHE_MISS"))

    result = await RegistryProvider(cache, Client(failure=True)).lookup(_server())

    assert result.status is HistoryStatus.UNKNOWN
    assert result.reason_code is HistoryReason.TIMEOUT
    assert cache.persisted is None
    assert result.diagnostics[0].code == "REGISTRY_FAILED"
