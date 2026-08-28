from datetime import UTC, datetime, timedelta

from panopticon.registry.cache import MemoryCache, cache_key, cache_path, lookup_history, make_lookup
from panopticon.registry.model import CacheRecord, HistoryReason, HistoryStatus, NormalizedHistory


def test_cache_miss_and_offline_are_explicit() -> None:
    lookup = make_lookup("npm", "pkg", "latest")
    result = lookup_history(MemoryCache(), lookup, offline=True)
    assert result.status is HistoryStatus.UNSUPPORTED
    assert result.reason_code is HistoryReason.OFFLINE
    assert cache_key(lookup) != cache_key(make_lookup("npm", "pkg", "1.0.0"))
    assert cache_path(lookup).startswith("~/.panopticon/")


def test_fresh_cache_is_available() -> None:
    lookup = make_lookup("pypi", "pkg", "1.0.0")
    history = NormalizedHistory(status=HistoryStatus.AVAILABLE, reason_code=HistoryReason.OK, ecosystem="pypi", name="pkg", requested_spec="1.0.0", resolved_version="1.0.0")
    record = CacheRecord(lookup=lookup, history=history, fetched_at=datetime(2025, 1, 1, tzinfo=UTC))
    result = lookup_history(MemoryCache((record,)), lookup, now=datetime(2025, 1, 2, tzinfo=UTC), max_age=timedelta(days=7))
    assert result.registry_fresh is True
