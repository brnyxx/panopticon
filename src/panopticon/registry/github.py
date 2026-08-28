"""GitHub release history normalization."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from .common import age, parse_timestamp, resolve, result, safe_url, semver_key, version
from .model import HistoryReason, HistoryStatus, NormalizedHistory, ReleaseRecord


def normalize_github(
    payload: object, *, name: str, spec: str, now: datetime | None = None
) -> NormalizedHistory:
    now = now or datetime.now(UTC)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("releases"), list):
        return result(
            "github",
            name,
            spec,
            status=HistoryStatus.INCOMPLETE,
            reason_code=HistoryReason.MALFORMED_INPUT,
        )
    records: list[ReleaseRecord] = []
    for item in payload["releases"]:
        if not isinstance(item, Mapping):
            continue
        ver = version(item.get("tag_name") or item.get("name"))
        if not ver:
            continue
        timestamp, reason = parse_timestamp(item.get("published_at"), now=now)
        if reason:
            return result("github", name, spec, status=HistoryStatus.INCOMPLETE, reason_code=reason)
        records.append(
            ReleaseRecord(
                version=ver,
                published_at=timestamp,
                age_days=age(timestamp, now) if timestamp else None,
                yanked=bool(item.get("draft")),
                deprecated=False,
            )
        )
    records.sort(key=lambda record: semver_key(record.version))
    resolved, reason = resolve(spec, records)
    return result(
        "github",
        name,
        spec,
        status=HistoryStatus.AVAILABLE if resolved else HistoryStatus.UNKNOWN,
        reason_code=reason,
        resolved_version=resolved,
        source_url=safe_url(payload.get("html_url") or payload.get("url")),
        archived=payload.get("archived") if isinstance(payload.get("archived"), bool) else None,
        releases=tuple(records),
    )
