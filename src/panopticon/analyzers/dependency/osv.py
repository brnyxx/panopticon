"""Bounded OSV advisory adapter for exact PyPI dependency versions."""

from __future__ import annotations

import tomllib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

import httpx
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from .model import DependencyInput
from .requirements import normalize_package_name
from .scan import AdvisoryResult, AdvisoryStatus, DependencyFinding

OSV_QUERY_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_TIMEOUT_SECONDS = 10.0
OSV_BATCH_LIMIT = 256
_SEVERITIES = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW"})


class OsvResponse(Protocol):
    status_code: int

    def json(self) -> object: ...


HttpPost = Callable[..., OsvResponse]


class OsvAdvisory:
    """Resolve exact local versions and query OSV without retaining responses."""

    def __init__(self, root: Path, *, post: HttpPost = httpx.post) -> None:
        self.root = root
        self.post = post

    def check(self, requirements: DependencyInput) -> AdvisoryResult:
        resolved = _resolve_versions(self.root, requirements)
        if resolved is None:
            return AdvisoryResult(AdvisoryStatus.INCOMPLETE, "ADVISORY_VERSION_UNRESOLVED")
        if len(resolved) > OSV_BATCH_LIMIT:
            return AdvisoryResult(AdvisoryStatus.INCOMPLETE, "ADVISORY_BATCH_TOO_LARGE")
        payload = {
            "queries": [
                {"package": {"name": name, "ecosystem": "PyPI"}, "version": version}
                for name, version in resolved
            ]
        }
        try:
            response = self.post(
                OSV_QUERY_BATCH_URL,
                json=payload,
                timeout=OSV_TIMEOUT_SECONDS,
                follow_redirects=False,
            )
        except (httpx.HTTPError, OSError):
            return AdvisoryResult(AdvisoryStatus.INCOMPLETE, "ADVISORY_NETWORK_ERROR")
        if response.status_code != 200:
            return AdvisoryResult(AdvisoryStatus.INCOMPLETE, "ADVISORY_NETWORK_ERROR")
        try:
            findings = _findings(response.json(), resolved)
        except (TypeError, ValueError):
            return AdvisoryResult(AdvisoryStatus.INCOMPLETE, "ADVISORY_RESPONSE_INVALID")
        return AdvisoryResult(AdvisoryStatus.COMPLETE, "COMPLETED", findings)


def _resolve_versions(
    root: Path, requirements: DependencyInput
) -> tuple[tuple[str, str], ...] | None:
    lock = root / "uv.lock"
    if lock.is_file() and not lock.is_symlink():
        return _locked_versions(lock, tuple(item.name for item in requirements.requirements))
    resolved = tuple(
        _exact_requirement(item.name, item.specifier) for item in requirements.requirements
    )
    if any(item is None for item in resolved):
        return None
    return tuple(sorted({item for item in resolved if item is not None}))


def _locked_versions(lock: Path, names: tuple[str, ...]) -> tuple[tuple[str, str], ...] | None:
    try:
        document = tomllib.loads(lock.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    packages = document.get("package")
    if not isinstance(packages, list):
        return None
    versions: dict[str, set[str]] = {}
    for package in packages:
        if not isinstance(package, Mapping):
            return None
        name, version = package.get("name"), package.get("version")
        if not isinstance(name, str) or not isinstance(version, str) or not _version(version):
            return None
        versions.setdefault(normalize_package_name(name), set()).add(version)
    resolved: list[tuple[str, str]] = []
    for name in sorted(set(names)):
        candidates = versions.get(name, set())
        if len(candidates) != 1:
            return None
        resolved.append((name, next(iter(candidates))))
    return tuple(resolved)


def _exact_requirement(name: str, specifier: str) -> tuple[str, str] | None:
    try:
        parsed = SpecifierSet(specifier)
    except ValueError:
        return None
    items = tuple(parsed)
    if len(items) != 1 or items[0].operator != "==" or "*" in items[0].version:
        return None
    version = items[0].version
    return (name, version) if _version(version) else None


def _version(value: str) -> bool:
    try:
        Version(value)
    except InvalidVersion:
        return False
    return True


def _findings(
    payload: object, resolved: Sequence[tuple[str, str]]
) -> tuple[DependencyFinding, ...]:
    if not isinstance(payload, Mapping):
        raise ValueError("response is not an object")
    results = payload.get("results")
    if not isinstance(results, list) or len(results) != len(resolved):
        raise ValueError("response cardinality is invalid")
    findings: set[DependencyFinding] = set()
    for result, (package, _version) in zip(results, resolved, strict=True):
        if not isinstance(result, Mapping):
            raise ValueError("result is not an object")
        vulnerabilities = result.get("vulns", [])
        if not isinstance(vulnerabilities, list):
            raise ValueError("vulnerabilities are not a list")
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, Mapping):
                raise ValueError("vulnerability is not an object")
            advisory_id, summary = vulnerability.get("id"), vulnerability.get("summary")
            if not isinstance(advisory_id, str) or not isinstance(summary, str):
                raise ValueError("vulnerability fields are invalid")
            findings.add(DependencyFinding(advisory_id, package, _severity(vulnerability), summary))
    return tuple(
        sorted(
            findings, key=lambda item: (item.advisory_id, item.package, item.severity, item.summary)
        )
    )


def _severity(vulnerability: Mapping[object, object]) -> str:
    for field in ("database_specific", "ecosystem_specific"):
        details = vulnerability.get(field)
        if isinstance(details, Mapping):
            value = details.get("severity")
            if isinstance(value, str) and value.upper() in _SEVERITIES:
                return value.upper()
    return "REVIEW"


__all__ = ["OSV_BATCH_LIMIT", "OSV_QUERY_BATCH_URL", "OSV_TIMEOUT_SECONDS", "OsvAdvisory"]
