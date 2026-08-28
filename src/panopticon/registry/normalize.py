"""Deterministic normalization of npm, PyPI and GitHub history responses."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .model import HistoryReason, HistoryStatus, NormalizedHistory, ReleaseRecord

_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")


def _safe_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        p = urlsplit(value)
        if p.scheme.casefold() not in {"http", "https"} or not p.hostname:
            return None
        host = p.hostname.encode("idna").decode().casefold()
        netloc = host + (f":{p.port}" if p.port else "")
        return urlunsplit((p.scheme.casefold(), netloc, p.path or "/", "", ""))
    except (ValueError, UnicodeError):
        return None


def parse_timestamp(value: Any) -> tuple[datetime | None, HistoryReason | None]:
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
    # Guard against absurd dates that can overflow age calculations.
    if parsed.year < 1970 or parsed > datetime.now(UTC):
        return None, HistoryReason.TIMESTAMP_TOO_LARGE
    return parsed, None


def _age(timestamp: datetime, now: datetime) -> int | None:
    seconds = (now - timestamp).total_seconds()
    if seconds < 0 or seconds > 36525 * 86400:
        return None
    return int(seconds // 86400)


def _version(value: Any) -> str | None:
    return value if isinstance(value, str) and _VERSION.fullmatch(value) else None


def _select(spec: str, versions: list[str]) -> str | None:
    if not isinstance(spec, str) or not spec.strip():
        return None
    spec = spec.strip()
    exact = _version(spec)
    if exact:
        return next((v for v in versions if v == spec or v == spec.removeprefix("v")), None)
    if spec in {"latest", "stable"}:
        return versions[-1] if versions else None
    # npm tags and a small deterministic range subset (>=, >, <=, <, ^, ~).
    if spec and not any(c in spec for c in "<>=^~*|"):
        return None
    candidates = [
        (v, tuple(map(int, _VERSION.fullmatch(v).groups()[:3])))
        for v in versions
        if _VERSION.fullmatch(v)
    ]
    if not candidates:
        return None
    checks = re.findall(r"(>=|<=|>|<|\^|~)?\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?", spec)

    def okay(t: tuple[int, int, int]) -> bool:
        for op, a, b, c in checks:
            base = (int(a), int(b or 0), int(c or 0))
            if op == ">=" and not t >= base:
                return False
            if op == "<=" and not t <= base:
                return False
            if op == ">" and not t > base:
                return False
            if op == "<" and not t < base:
                return False
            if op == "^" and not (t >= base and t[0] == base[0]):
                return False
            if op == "~" and not (t >= base and t[:2] == base[:2]):
                return False
        return True

    matched = [v for v, t in candidates if okay(t)]
    return matched[-1] if matched else None


def _result(ecosystem: str, name: str, spec: str, **kwargs: Any) -> NormalizedHistory:
    return NormalizedHistory(ecosystem=ecosystem, name=name, requested_spec=spec, **kwargs)


def normalize_npm(
    payload: Mapping[str, Any], *, name: str, spec: str, now: datetime | None = None
) -> NormalizedHistory:
    return _normalize_registry("npm", payload, name=name, spec=spec, now=now)


def normalize_pypi(
    payload: Mapping[str, Any], *, name: str, spec: str, now: datetime | None = None
) -> NormalizedHistory:
    return _normalize_registry("pypi", payload, name=name, spec=spec, now=now)


def normalize_github(
    payload: Mapping[str, Any], *, name: str, spec: str, now: datetime | None = None
) -> NormalizedHistory:
    now = now or datetime.now(UTC)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("releases"), list):
        return _result(
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
        ver = _version(item.get("tag_name") or item.get("name"))
        if not ver:
            continue
        ts, reason = parse_timestamp(item.get("published_at"))
        if reason:
            return _result(
                "github", name, spec, status=HistoryStatus.INCOMPLETE, reason_code=reason
            )
        records.append(
            ReleaseRecord(
                version=ver,
                published_at=ts,
                age_days=_age(ts, now) if ts else None,
                yanked=bool(item.get("draft")),
                deprecated=False,
            )
        )
    records.sort(key=lambda r: r.version)
    resolved = _select(spec, [r.version for r in records])
    return _result(
        "github",
        name,
        spec,
        status=HistoryStatus.AVAILABLE if resolved else HistoryStatus.UNKNOWN,
        reason_code=HistoryReason.OK if resolved else HistoryReason.UNRESOLVED_SPEC,
        resolved_version=resolved,
        source_url=_safe_url(payload.get("html_url") or payload.get("url")),
        releases=tuple(records),
    )


# Explicit aliases make the ecosystem boundary easy to discover and keep the
# public API stable for integrations.
normalize_npm_history = normalize_npm
normalize_pypi_history = normalize_pypi
normalize_github_history = normalize_github


def normalize_registry_history(
    ecosystem: str,
    payload: Mapping[str, Any],
    *,
    name: str,
    spec: str,
    now: datetime | None = None,
) -> NormalizedHistory:
    ecosystem = ecosystem.casefold()
    if ecosystem == "npm":
        return normalize_npm(payload, name=name, spec=spec, now=now)
    if ecosystem in {"pypi", "python"}:
        return normalize_pypi(payload, name=name, spec=spec, now=now)
    if ecosystem in {"github", "git"}:
        return normalize_github(payload, name=name, spec=spec, now=now)
    return _result(
        ecosystem,
        name,
        spec,
        status=HistoryStatus.UNSUPPORTED,
        reason_code=HistoryReason.UNSUPPORTED_ECOSYSTEM,
    )


def _normalize_registry(
    ecosystem: str, payload: Mapping[str, Any], *, name: str, spec: str, now: datetime | None
) -> NormalizedHistory:
    now = now or datetime.now(UTC)
    if not isinstance(payload, Mapping):
        return _result(
            ecosystem,
            name,
            spec,
            status=HistoryStatus.INCOMPLETE,
            reason_code=HistoryReason.MALFORMED_INPUT,
        )
    latest: str | None = None
    maintainers: tuple[str, ...] = ()
    archived: bool | None = None
    if ecosystem == "npm":
        versions = payload.get("versions")
        times = payload.get("time", {})
        repository = payload.get("repository")
        source = payload.get("homepage")
        if not source and isinstance(repository, Mapping):
            source = repository.get("url")
        tags = payload.get("dist-tags")
        latest = (
            tags.get("latest")
            if isinstance(tags, Mapping) and isinstance(tags.get("latest"), str)
            else None
        )
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
        times = {
            v: (
                items[0].get("upload_time_iso_8601")
                if items and isinstance(items[0], Mapping)
                else None
            )
            for v, items in (versions or {}).items()
        }
        source = info.get("project_url") if isinstance(info, Mapping) else None
        latest = (
            info.get("version")
            if isinstance(info, Mapping) and isinstance(info.get("version"), str)
            else None
        )
    if not isinstance(versions, Mapping):
        return _result(
            ecosystem,
            name,
            spec,
            status=HistoryStatus.INCOMPLETE,
            reason_code=HistoryReason.MALFORMED_INPUT,
        )
    records: list[ReleaseRecord] = []
    for ver in sorted(versions):
        if not _version(ver):
            continue
        ts, reason = parse_timestamp(times.get(ver) if isinstance(times, Mapping) else None)
        if reason:
            return _result(
                ecosystem, name, spec, status=HistoryStatus.INCOMPLETE, reason_code=reason
            )
        meta = versions[ver] if isinstance(versions[ver], Mapping) else {}
        yanked = bool(meta.get("yanked")) if ecosystem == "pypi" else False
        dep = bool(meta.get("deprecated")) if ecosystem == "npm" else False
        records.append(
            ReleaseRecord(
                version=ver,
                published_at=ts,
                age_days=_age(ts, now) if ts else None,
                yanked=yanked,
                deprecated=dep,
            )
        )
    resolved = _select(spec, [r.version for r in records if not r.yanked and not r.deprecated])
    return _result(
        ecosystem,
        name,
        spec,
        status=HistoryStatus.AVAILABLE if resolved else HistoryStatus.UNKNOWN,
        reason_code=HistoryReason.OK if resolved else HistoryReason.UNRESOLVED_SPEC,
        resolved_version=resolved,
        latest=latest,
        maintainers=maintainers,
        archived=archived,
        source_url=_safe_url(source),
        releases=tuple(records),
    )
