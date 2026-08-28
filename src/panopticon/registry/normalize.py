"""Deterministic normalization of npm, PyPI and GitHub history responses."""

from __future__ import annotations

from datetime import datetime

from .common import (
    age as _age,
    normalize_registry as _normalize_registry,
    parse_timestamp,
    resolve as _resolve,
    result as _result,
    safe_url as _safe_url,
    select as _select,
    semver_key as _semver_key,
    version as _version,
)
from .github import normalize_github
from .model import HistoryReason, HistoryStatus, NormalizedHistory
from .npm import normalize_npm
from .pypi import normalize_pypi


# Explicit aliases make the ecosystem boundary easy to discover and keep the
# public API stable for integrations.
normalize_npm_history = normalize_npm
normalize_pypi_history = normalize_pypi
normalize_github_history = normalize_github


def normalize_registry_history(
    ecosystem: str,
    payload: object,
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


__all__ = [
    "normalize_github",
    "normalize_github_history",
    "normalize_npm",
    "normalize_npm_history",
    "normalize_pypi",
    "normalize_pypi_history",
    "normalize_registry_history",
    "parse_timestamp",
]
