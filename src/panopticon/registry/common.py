"""Shared normalization helpers for registry history."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from .model import HistoryReason, HistoryStatus, NormalizedHistory, ReleaseRecord

_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")


def safe_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.removeprefix("git+")
    try:
        parsed = urlsplit(raw)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            return None
        host = parsed.hostname.encode("idna").decode().casefold()
        netloc = host + (f":{parsed.port}" if parsed.port else "")
        return urlunsplit((parsed.scheme.casefold(), netloc, parsed.path or "/", "", ""))
    except (ValueError, UnicodeError):
        return None


def parse_timestamp(
    value: object, *, now: datetime | None = None
) -> tuple[datetime | None, HistoryReason | None]:
    if value is None:
        return None, HistoryReason.MISSING_TIMESTAMP
    if not isinstance(value, str):
        return None, HistoryReason.INVALID_TIMESTAMP
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, HistoryReason.INVALID_TIMESTAMP
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, HistoryReason.INVALID_TIMESTAMP
    parsed = parsed.astimezone(UTC)
    if parsed.year < 1970 or parsed > (now or datetime.now(UTC)):
        return None, HistoryReason.TIMESTAMP_TOO_LARGE
    return parsed, None


def age(timestamp: datetime, now: datetime) -> int | None:
    seconds = (now - timestamp).total_seconds()
    if seconds < 0 or seconds > 36525 * 86400:
        return None
    return int(seconds // 86400)


def version(value: object) -> str | None:
    return value if isinstance(value, str) and _VERSION.fullmatch(value) else None


def semver_key(value: str) -> tuple[int, int, int, str]:
    matched = _VERSION.fullmatch(value)
    if matched is None:
        return (0, 0, 0, value)
    major, minor, patch = matched.groups()[:3]
    return (int(major), int(minor), int(patch), value)


def select(spec: str, versions: list[str]) -> str | None:
    if not isinstance(spec, str) or not spec.strip():
        return None
    spec = spec.strip()
    exact = version(spec)
    if exact:
        return next((v for v in versions if v == spec or v == spec.removeprefix("v")), None)
    if spec in {"latest", "stable"}:
        return versions[-1] if versions else None
    if spec and not any(c in spec for c in "<>=^~*|"):
        return None
    candidates: list[tuple[str, tuple[int, int, int]]] = []
    for item in versions:
        matched = _VERSION.fullmatch(item)
        if matched is not None:
            major, minor, patch = matched.groups()[:3]
            candidates.append((item, (int(major), int(minor), int(patch))))
    if not candidates:
        return None
    checks = re.findall(r"(>=|<=|>|<|\^|~)?\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?", spec)

    def okay(target: tuple[int, int, int]) -> bool:
        for op, major, minor, patch in checks:
            base = (int(major), int(minor or 0), int(patch or 0))
            if op == ">=" and not target >= base:
                return False
            if op == "<=" and not target <= base:
                return False
            if op == ">" and not target > base:
                return False
            if op == "<" and not target < base:
                return False
            if op == "^" and not (target >= base and target[0] == base[0]):
                return False
            if op == "~" and not (target >= base and target[:2] == base[:2]):
                return False
        return True

    matching_versions = [
        item for item, target in sorted(candidates, key=lambda pair: pair[1]) if okay(target)
    ]
    return matching_versions[-1] if matching_versions else None


def resolve(
    spec: str, records: list[ReleaseRecord], tags: Mapping[str, object] | None = None
) -> tuple[str | None, HistoryReason]:
    effective = tags.get(spec, spec) if tags is not None else spec
    if not isinstance(effective, str):
        return None, HistoryReason.UNRESOLVED_SPEC
    exact = version(effective)
    if exact is not None:
        selected = next(
            (
                record
                for record in records
                if record.version == exact
                or record.version.removeprefix("v") == exact.removeprefix("v")
            ),
            None,
        )
        if selected is None:
            return None, HistoryReason.UNRESOLVED_SPEC
        if selected.yanked:
            return selected.version, HistoryReason.YANKED
        if selected.deprecated:
            return selected.version, HistoryReason.DEPRECATED
        return selected.version, HistoryReason.OK
    usable = [record.version for record in records if not record.yanked and not record.deprecated]
    resolved = select(effective, usable)
    return resolved, HistoryReason.OK if resolved else HistoryReason.UNRESOLVED_SPEC


def result(
    ecosystem: str,
    name: str,
    spec: str,
    *,
    status: HistoryStatus,
    reason_code: HistoryReason,
    resolved_version: str | None = None,
    source_url: str | None = None,
    latest: str | None = None,
    maintainers: tuple[str, ...] = (),
    archived: bool | None = None,
    releases: tuple[ReleaseRecord, ...] = (),
) -> NormalizedHistory:
    return NormalizedHistory(
        ecosystem=ecosystem,
        name=name,
        requested_spec=spec,
        status=status,
        reason_code=reason_code,
        resolved_version=resolved_version,
        source_url=source_url,
        latest=latest,
        maintainers=maintainers,
        archived=archived,
        releases=releases,
    )


def normalize_registry(
    ecosystem: str, payload: object, *, name: str, spec: str, now: datetime | None
) -> NormalizedHistory:
    now = now or datetime.now(UTC)
    if not isinstance(payload, Mapping):
        return result(
            ecosystem,
            name,
            spec,
            status=HistoryStatus.INCOMPLETE,
            reason_code=HistoryReason.MALFORMED_INPUT,
        )
    tags: Mapping[str, object] | None = None
    maintainers: tuple[str, ...] = ()
    if ecosystem == "npm":
        versions = payload.get("versions")
        times = payload.get("time", {})
        repository = payload.get("repository")
        source = payload.get("homepage")
        if not source and isinstance(repository, Mapping):
            source = repository.get("url")
        raw_tags = payload.get("dist-tags")
        tags = raw_tags if isinstance(raw_tags, Mapping) else None
        latest_value = tags.get("latest") if tags is not None else None
        latest = latest_value if isinstance(latest_value, str) else None
        raw = payload.get("maintainers")
        if isinstance(raw, list):
            maintainers = tuple(
                sorted(
                    m["name"]
                    for m in raw
                    if isinstance(m, Mapping) and isinstance(m.get("name"), str)
                )
            )
    else:
        info = payload.get("info", {})
        versions = payload.get("releases")
        release_mapping = versions if isinstance(versions, Mapping) else {}
        times = {
            v: (
                items[0].get("upload_time_iso_8601")
                if items and isinstance(items[0], Mapping)
                else None
            )
            for v, items in release_mapping.items()
        }
        source = info.get("project_url") if isinstance(info, Mapping) else None
        latest = (
            info.get("version")
            if isinstance(info, Mapping) and isinstance(info.get("version"), str)
            else None
        )
    if not isinstance(versions, Mapping):
        return result(
            ecosystem,
            name,
            spec,
            status=HistoryStatus.INCOMPLETE,
            reason_code=HistoryReason.MALFORMED_INPUT,
        )
    records: list[ReleaseRecord] = []
    for ver in sorted(versions):
        if not version(ver):
            continue
        timestamp, reason = parse_timestamp(
            times.get(ver) if isinstance(times, Mapping) else None, now=now
        )
        if reason:
            return result(
                ecosystem, name, spec, status=HistoryStatus.INCOMPLETE, reason_code=reason
            )
        raw_meta = versions[ver]
        meta = raw_meta if isinstance(raw_meta, Mapping) else {}
        files = raw_meta if isinstance(raw_meta, list) else ()
        yanked = (
            any(isinstance(item, Mapping) and bool(item.get("yanked")) for item in files)
            if ecosystem == "pypi"
            else False
        )
        deprecated = bool(meta.get("deprecated")) if ecosystem == "npm" else False
        records.append(
            ReleaseRecord(
                version=ver,
                published_at=timestamp,
                age_days=age(timestamp, now) if timestamp else None,
                yanked=yanked,
                deprecated=deprecated,
            )
        )
    records.sort(key=lambda record: semver_key(record.version))
    resolved, reason = resolve(spec, records, tags if ecosystem == "npm" else None)
    return result(
        ecosystem,
        name,
        spec,
        status=HistoryStatus.AVAILABLE if resolved else HistoryStatus.UNKNOWN,
        reason_code=reason,
        resolved_version=resolved,
        latest=latest,
        maintainers=maintainers,
        source_url=safe_url(source),
        releases=tuple(records),
    )
