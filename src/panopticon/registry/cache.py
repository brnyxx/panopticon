"""Typed normalized registry cache with store-backed persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum, unique
from hashlib import sha256
from typing import Protocol

from pydantic import ValidationError, model_validator

from panopticon.models.common import SchemaVersion, StrictModel
from panopticon.store.contracts import ModelArtifact, PersistRequest, PersistSuccess, SinkKind
from panopticon.store.repository import ArtifactRepository

from .history import SnapshotSeries
from .model import (
    CacheLookup,
    CacheRecord,
    HistoryReason,
    HistoryStatus,
    NormalizedHistory,
)

CACHE_TTL = timedelta(hours=24)


class CacheEnvelope(StrictModel):
    """Strict normalized cache persistence model."""

    schema_version: SchemaVersion = "1.0"
    ecosystem: str
    name: str
    snapshots: SnapshotSeries
    etags: tuple[tuple[str, str], ...] = ()
    fetched_at: datetime

    @model_validator(mode="after")
    def validate_envelope(self) -> CacheEnvelope:
        if self.fetched_at.utcoffset() != timedelta(0):
            raise ValueError("fetched_at must be UTC")
        if not self.snapshots.snapshots:
            raise ValueError("cache requires at least one normalized snapshot")
        if len(self.etags) > 3:
            raise ValueError("at most three resource etags are allowed")
        resources = [resource for resource, _ in self.etags]
        if resources != sorted(set(resources)):
            raise ValueError("etags must be unique and sorted")
        if any(
            not resource
            or not value
            or len(value) > 256
            or any(character in value for character in "\r\n\0")
            for resource, value in self.etags
        ):
            raise ValueError("invalid etag")
        return self


class Cache(Protocol):
    def get(self, lookup: CacheLookup) -> CacheRecord | None: ...


class MemoryCache:
    def __init__(self, records: tuple[CacheRecord, ...] = ()) -> None:
        self._records = {cache_key(r.lookup): r for r in records}

    def get(self, lookup: CacheLookup) -> CacheRecord | None:
        return self._records.get(cache_key(lookup))


def cache_key(lookup: CacheLookup) -> str:
    value = f"{lookup.ecosystem.casefold()}\0{lookup.name.casefold()}"
    return sha256(value.encode("utf-8")).hexdigest()


def cache_path(lookup: CacheLookup) -> str:
    return f"~/.panopticon/cache/registry/{lookup.ecosystem.casefold()}/{cache_key(lookup)}.json"


def make_lookup(ecosystem: str, name: str, spec: str) -> CacheLookup:
    return CacheLookup(ecosystem=ecosystem.casefold(), name=name.strip(), spec=spec.strip())


@unique
class CacheLoadStatus(StrEnum):
    HIT = "HIT"
    MISS = "MISS"
    STALE = "STALE"
    FUTURE = "FUTURE"
    INVALID = "INVALID"
    PERMISSION = "PERMISSION"
    SYMLINK = "SYMLINK"
    PERSIST_FAILURE = "PERSIST_FAILURE"


@dataclass(frozen=True, slots=True)
class CacheLoad:
    status: CacheLoadStatus
    envelope: CacheEnvelope | None = None
    reason_code: str = "OK"


class PersistentCache:
    """Repository adapter. Reads strict JSON and delegates all writes to the store."""

    def __init__(self, repository: ArtifactRepository) -> None:
        self.repository = repository

    def load(self, lookup: CacheLookup, *, now: datetime | None = None) -> CacheLoad:
        path = (
            self.repository.root
            / "cache"
            / "registry"
            / lookup.ecosystem.casefold()
            / f"{cache_key(lookup)}.json"
        )
        if path.is_symlink() or path.parent.is_symlink():
            return CacheLoad(CacheLoadStatus.SYMLINK, reason_code="SYMLINK_REJECTED")
        try:
            payload = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return CacheLoad(CacheLoadStatus.MISS, reason_code="CACHE_MISS")
        except PermissionError:
            return CacheLoad(CacheLoadStatus.PERMISSION, reason_code="CACHE_PERMISSION")
        except OSError:
            return CacheLoad(CacheLoadStatus.INVALID, reason_code="CACHE_READ_FAILED")
        try:
            envelope = CacheEnvelope.model_validate_json(payload)
        except (ValidationError, ValueError, UnicodeError):
            return CacheLoad(CacheLoadStatus.INVALID, reason_code="CACHE_INVALID")
        if (
            envelope.ecosystem.casefold() != lookup.ecosystem.casefold()
            or envelope.name.casefold() != lookup.name.casefold()
        ):
            return CacheLoad(CacheLoadStatus.INVALID, reason_code="CACHE_IDENTITY_MISMATCH")
        current = now or datetime.now(UTC)
        age = current - envelope.fetched_at
        if age < timedelta(0):
            return CacheLoad(CacheLoadStatus.FUTURE, envelope, "CACHE_FUTURE")
        if age > CACHE_TTL:
            return CacheLoad(CacheLoadStatus.STALE, envelope, "CACHE_STALE")
        return CacheLoad(CacheLoadStatus.HIT, envelope)

    def persist(self, lookup: CacheLookup, envelope: CacheEnvelope) -> CacheLoad:
        target = (
            self.repository.root
            / "cache"
            / "registry"
            / lookup.ecosystem.casefold()
            / f"{cache_key(lookup)}.json"
        )
        result = self.repository.persist_request(
            PersistRequest(target, ModelArtifact(SinkKind.CACHE, envelope))
        )
        if isinstance(result, PersistSuccess):
            return CacheLoad(CacheLoadStatus.HIT, envelope)
        return CacheLoad(CacheLoadStatus.PERSIST_FAILURE, reason_code="CACHE_PERSIST_FAILED")


def lookup_history(
    cache: Cache,
    lookup: CacheLookup,
    *,
    offline: bool = False,
    now: datetime | None = None,
    max_age: timedelta = CACHE_TTL,
) -> NormalizedHistory:
    now = now or datetime.now(UTC)
    record = cache.get(lookup)
    if record is None:
        return NormalizedHistory(
            status=HistoryStatus.UNKNOWN,
            reason_code=HistoryReason.OFFLINE if offline else HistoryReason.CACHE_MISS,
            ecosystem=lookup.ecosystem,
            name=lookup.name,
            requested_spec=lookup.spec,
        )
    fetched = record.fetched_at
    if fetched.utcoffset() != timedelta(0) or fetched > now or now - fetched > max_age:
        return record.history.model_copy(
            update={
                "status": HistoryStatus.UNKNOWN,
                "reason_code": HistoryReason.STALE_CACHE,
                "registry_fresh": False,
            }
        )
    return record.history.model_copy(
        update={"registry_fetched_at": fetched, "registry_fresh": True}
    )


def resolve_cached_version(lookup: CacheLookup, cache: Cache) -> str | None:
    history = lookup_history(cache, lookup)
    return history.resolved_version if history.status is HistoryStatus.AVAILABLE else None


StoreCache = PersistentCache
CacheStatus = CacheLoadStatus
