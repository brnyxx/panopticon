"""Deterministic, read-only cache protocol for normalized registry records."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Protocol

from .model import CacheLookup, CacheRecord, HistoryReason, HistoryStatus, NormalizedHistory


class Cache(Protocol):
    def get(self, lookup: CacheLookup) -> CacheRecord | None: ...


class MemoryCache:
    """Small immutable-value cache adapter; persistence is deliberately store-owned."""

    def __init__(self, records: tuple[CacheRecord, ...] = ()) -> None:
        self._records = {cache_key(r.lookup): r for r in records}

    def get(self, lookup: CacheLookup) -> CacheRecord | None:
        return self._records.get(cache_key(lookup))


def cache_key(lookup: CacheLookup) -> str:
    """Stable key containing only normalized public lookup components."""
    value = f"{lookup.ecosystem.casefold()}\0{lookup.name.casefold()}\0{lookup.spec.strip()}"
    return sha256(value.encode("utf-8")).hexdigest()


def cache_path(lookup: CacheLookup) -> str:
    """Return the ``~``-relative store destination; this function never writes."""
    safe_name = lookup.name.replace("/", "__").replace("\\", "__")
    return f"~/.panopticon/cache/registry/{lookup.ecosystem.casefold()}/{safe_name}.json"


def make_lookup(ecosystem: str, name: str, spec: str) -> CacheLookup:
    return CacheLookup(ecosystem=ecosystem.casefold(), name=name.strip(), spec=spec.strip())


def lookup_history(
    cache: Cache,
    lookup: CacheLookup,
    *,
    offline: bool = False,
    now: datetime | None = None,
    max_age: timedelta = timedelta(days=7),
) -> NormalizedHistory:
    """Return cache value or an explicit status; never silently treats misses as success."""
    now = now or datetime.now(UTC)
    record = cache.get(lookup)
    if record is None:
        status = HistoryStatus.UNSUPPORTED if offline else HistoryStatus.UNKNOWN
        reason = HistoryReason.OFFLINE if offline else HistoryReason.CACHE_MISS
        return NormalizedHistory(
            status=status,
            reason_code=reason,
            ecosystem=lookup.ecosystem,
            name=lookup.name,
            requested_spec=lookup.spec,
        )
    fetched = record.fetched_at
    if fetched.utcoffset() != timedelta(0) or fetched > now or now - fetched > max_age:
        history = record.history.model_copy(update={"registry_fresh": False})
        return history.model_copy(
            update={"status": HistoryStatus.UNKNOWN, "reason_code": HistoryReason.STALE_CACHE}
        )
    return record.history.model_copy(
        update={"registry_fetched_at": fetched, "registry_fresh": True}
    )


def resolve_cached_version(lookup: CacheLookup, cache: Cache) -> str | None:
    """Resolve only a normalized exact/tag/range result from cache."""
    history = lookup_history(cache, lookup)
    return history.resolved_version if history.status is HistoryStatus.AVAILABLE else None


# Compatibility helper for callers that pass the inventory PackageIdentity.
def resolve_package_version(package: object, cache: Cache) -> str | None:
    ecosystem = getattr(
        getattr(package, "ecosystem", None), "value", getattr(package, "ecosystem", "")
    )
    name = getattr(package, "name", "")
    spec = getattr(package, "pinned", None) or "latest"
    return resolve_cached_version(make_lookup(str(ecosystem), str(name), str(spec)), cache)
