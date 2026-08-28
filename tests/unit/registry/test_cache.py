from datetime import UTC, datetime, timedelta

from panopticon.registry.cache import (
    CacheEnvelope,
    CacheLoadStatus,
    MemoryCache,
    PersistentCache,
    cache_key,
    cache_path,
    lookup_history,
    make_lookup,
    resolve_cached_version,
)
from panopticon.registry.history import SnapshotSeries
from panopticon.registry.model import CacheRecord, HistoryReason, HistoryStatus, NormalizedHistory
from panopticon.store import ArtifactRepository


def test_cache_miss_and_offline_are_explicit() -> None:
    lookup = make_lookup("npm", "pkg", "latest")
    result = lookup_history(MemoryCache(), lookup, offline=True)
    assert result.status is HistoryStatus.UNKNOWN
    assert result.reason_code is HistoryReason.OFFLINE
    assert cache_key(lookup) == cache_key(make_lookup("npm", "pkg", "1.0.0"))
    assert cache_path(lookup).startswith("~/.panopticon/")
    assert ".." not in cache_path(make_lookup("npm", "../../escape", "latest"))


def test_fresh_cache_is_available() -> None:
    lookup = make_lookup("pypi", "pkg", "1.0.0")
    history = NormalizedHistory(
        status=HistoryStatus.AVAILABLE,
        reason_code=HistoryReason.OK,
        ecosystem="pypi",
        name="pkg",
        requested_spec="1.0.0",
        resolved_version="1.0.0",
    )
    record = CacheRecord(
        lookup=lookup, history=history, fetched_at=datetime(2025, 1, 1, tzinfo=UTC)
    )
    result = lookup_history(
        MemoryCache((record,)),
        lookup,
        now=datetime(2025, 1, 2, tzinfo=UTC),
        max_age=timedelta(days=7),
    )
    assert result.registry_fresh is True
    assert result.registry_fetched_at == record.fetched_at
    assert resolve_cached_version(lookup, MemoryCache((record,))) is None


def test_stale_and_future_cache_records_are_unknown() -> None:
    lookup = make_lookup("npm", "pkg", "1.0.0")
    history = NormalizedHistory(
        status=HistoryStatus.AVAILABLE,
        reason_code=HistoryReason.OK,
        ecosystem="npm",
        name="pkg",
        requested_spec="1.0.0",
        resolved_version="1.0.0",
    )
    stale = CacheRecord(
        lookup=lookup,
        history=history,
        fetched_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    future = stale.model_copy(update={"fetched_at": datetime(2026, 1, 1, tzinfo=UTC)})
    now = datetime(2025, 1, 1, tzinfo=UTC)

    for record in (stale, future):
        result = lookup_history(
            MemoryCache((record,)),
            lookup,
            now=now,
            max_age=timedelta(days=7),
        )
        assert result.status is HistoryStatus.UNKNOWN
        assert result.reason_code is HistoryReason.STALE_CACHE
        assert result.registry_fresh is False


def test_persistent_cache_round_trips_at_exact_ttl_boundary(tmp_path) -> None:
    lookup = make_lookup("npm", "pkg", "latest")
    fetched = datetime(2025, 1, 1, tzinfo=UTC)
    envelope = CacheEnvelope(
        ecosystem="npm",
        name="pkg",
        snapshots=SnapshotSeries(),
        etags=(("package", '"etag"'),),
        fetched_at=fetched,
    )
    cache = PersistentCache(ArtifactRepository(tmp_path))

    assert cache.persist(lookup, envelope).status is CacheLoadStatus.HIT
    assert cache.load(lookup, now=fetched + timedelta(hours=24)).status is CacheLoadStatus.HIT
    stale = cache.load(lookup, now=fetched + timedelta(hours=24, microseconds=1))
    assert stale.status is CacheLoadStatus.STALE
    assert stale.envelope == envelope
