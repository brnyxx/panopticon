"""Normalized registry snapshots and deterministic history transitions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from .model import NormalizedHistory


class TransitionStatus(StrEnum):
    CHANGED = "CHANGED"
    UNCHANGED = "UNCHANGED"
    UNKNOWN = "UNKNOWN"


class HistoryTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    status: TransitionStatus
    added_releases: tuple[str, ...] = ()
    removed_releases: tuple[str, ...] = ()
    added_maintainers: tuple[str, ...] = ()
    removed_maintainers: tuple[str, ...] = ()
    reason_code: str


class RegistrySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    observed_at: datetime
    history: NormalizedHistory
    etag: str | None = None
    transition: HistoryTransition

    @field_validator("observed_at")
    @classmethod
    def require_aware_observation(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value


class SnapshotSeries(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    snapshots: tuple[RegistrySnapshot, ...] = ()


def transition(
    previous: NormalizedHistory | None,
    current: NormalizedHistory,
) -> HistoryTransition:
    if previous is None:
        return HistoryTransition(
            status=TransitionStatus.UNKNOWN,
            reason_code="FIRST_OBSERVATION",
        )
    previous_versions = {release.version for release in previous.releases}
    current_versions = {release.version for release in current.releases}
    previous_maintainers = set(previous.maintainers)
    current_maintainers = set(current.maintainers)
    added_releases = tuple(sorted(current_versions - previous_versions))
    removed_releases = tuple(sorted(previous_versions - current_versions))
    added_maintainers = tuple(sorted(current_maintainers - previous_maintainers))
    removed_maintainers = tuple(sorted(previous_maintainers - current_maintainers))
    changed = any((added_releases, removed_releases, added_maintainers, removed_maintainers))
    return HistoryTransition(
        status=TransitionStatus.CHANGED if changed else TransitionStatus.UNCHANGED,
        added_releases=added_releases,
        removed_releases=removed_releases,
        added_maintainers=added_maintainers,
        removed_maintainers=removed_maintainers,
        reason_code="HISTORY_CHANGED" if changed else "NO_CHANGE",
    )


def append_snapshot(
    series: SnapshotSeries,
    history: NormalizedHistory,
    *,
    observed_at: datetime,
    etag: str | None = None,
) -> SnapshotSeries:
    previous = series.snapshots[-1].history if series.snapshots else None
    snapshot = RegistrySnapshot(
        observed_at=observed_at,
        history=history,
        etag=_safe_etag(etag),
        transition=transition(previous, history),
    )
    return SnapshotSeries(snapshots=(*series.snapshots, snapshot))


def _safe_etag(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) > 256 or any(character in value for character in "\r\n\0"):
        return None
    return value
