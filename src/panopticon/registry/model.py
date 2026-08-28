"""Typed registry-history and cache boundary models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum, unique

from pydantic import BaseModel, ConfigDict, Field, model_validator


@unique
class HistoryStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"
    INCOMPLETE = "INCOMPLETE"


@unique
class HistoryReason(StrEnum):
    OK = "OK"
    REGISTRY_FAILURE = "REGISTRY_FAILURE"
    OFFLINE = "OFFLINE"
    CACHE_MISS = "CACHE_MISS"
    MALFORMED_INPUT = "MALFORMED_INPUT"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
    TIMESTAMP_TOO_LARGE = "TIMESTAMP_TOO_LARGE"
    UNRESOLVED_SPEC = "UNRESOLVED_SPEC"
    UNSUPPORTED_ECOSYSTEM = "UNSUPPORTED_ECOSYSTEM"
    YANKED = "YANKED"
    DEPRECATED = "DEPRECATED"
    STALE_CACHE = "STALE_CACHE"


class ReleaseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: str
    published_at: datetime | None = None
    age_days: int | None = Field(default=None, ge=0)
    yanked: bool = False
    deprecated: bool = False


class NormalizedHistory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    status: HistoryStatus
    reason_code: HistoryReason
    ecosystem: str
    name: str
    requested_spec: str
    resolved_version: str | None = None
    source_url: str | None = None
    repository_url: str | None = None
    latest: str | None = None
    maintainers: tuple[str, ...] = ()
    archived: bool | None = None
    releases: tuple[ReleaseRecord, ...] = ()
    registry_fetched_at: datetime | None = None
    registry_fresh: bool | None = None


class CacheLookup(BaseModel):
    """Credential-free, deterministic cache lookup input."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    ecosystem: str
    name: str
    spec: str


class CacheRecord(BaseModel):
    """Normalized cache value; raw registry payloads are intentionally absent."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    lookup: CacheLookup
    history: NormalizedHistory
    fetched_at: datetime

    @model_validator(mode="after")
    def utc_fetched_at(self) -> CacheRecord:
        offset = self.fetched_at.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError("fetched_at must be UTC")
        return self


# Friendly aliases used by callers.
NormalizedRelease = ReleaseRecord
HistoryResult = NormalizedHistory
