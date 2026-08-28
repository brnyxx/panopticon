"""Deterministic daily rotation, lock, and retention plans."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import PurePosixPath


@dataclass(frozen=True, slots=True)
class RotationPlan:
    current: str
    lock: str
    stale: tuple[str, ...]


def utc_day(now: datetime) -> date:
    if now.tzinfo is None:
        raise ValueError("timezone required")
    return now.astimezone(UTC).date()


def rotation_plan(root: str, server_id: str, now: datetime, *, keep_days: int = 30) -> RotationPlan:
    if keep_days < 1:
        raise ValueError("keep_days must be positive")
    day = utc_day(now)
    base = PurePosixPath(root) / server_id
    current = str(base / f"{day.isoformat()}.ndjson")
    stale = tuple(
        str(base / f"{day - timedelta(days=offset)}.ndjson")
        for offset in range(keep_days, keep_days + 31)
    )
    return RotationPlan(current, current + ".lock", stale)


def lock_path(record_path: str) -> str:
    return record_path + ".lock"


def retention_paths(
    root: str, server_id: str, now: datetime, *, keep_days: int = 30
) -> tuple[str, ...]:
    return rotation_plan(root, server_id, now, keep_days=keep_days).stale
