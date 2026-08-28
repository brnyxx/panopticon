"""Dependency advisory boundary with explicit cache and offline states."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from .model import DependencyInput, DependencyStatus
from .requirements import collect_dependency_input


class AdvisoryStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_REQUESTED = "NOT_REQUESTED"


@dataclass(frozen=True, slots=True)
class DependencyFinding:
    advisory_id: str
    package: str
    severity: str
    summary: str


@dataclass(frozen=True, slots=True)
class AdvisoryResult:
    status: AdvisoryStatus
    reason_code: str
    findings: tuple[DependencyFinding, ...] = ()


class AdvisoryPort(Protocol):
    def check(self, requirements: DependencyInput) -> AdvisoryResult: ...


@dataclass(frozen=True, slots=True)
class DependencyScan:
    input: DependencyInput
    advisory: AdvisoryResult


def run_dependency_scan(
    root: Path,
    advisory: AdvisoryPort | None = None,
    *,
    offline: bool = False,
    cache_available: bool = True,
) -> DependencyScan:
    dependency_input = collect_dependency_input(root)
    if dependency_input.status is not DependencyStatus.COMPLETE:
        return DependencyScan(
            dependency_input,
            AdvisoryResult(AdvisoryStatus.NOT_REQUESTED, "DEPENDENCY_INPUT_INCOMPLETE"),
        )
    if offline:
        return DependencyScan(
            dependency_input,
            AdvisoryResult(AdvisoryStatus.UNSUPPORTED, "OFFLINE"),
        )
    if advisory is None:
        return DependencyScan(
            dependency_input,
            AdvisoryResult(AdvisoryStatus.INCOMPLETE, "ADVISORY_PROVIDER_UNAVAILABLE"),
        )
    if not cache_available:
        return DependencyScan(
            dependency_input,
            AdvisoryResult(AdvisoryStatus.INCOMPLETE, "ADVISORY_CACHE_UNAVAILABLE"),
        )
    return DependencyScan(dependency_input, advisory.check(dependency_input))


__all__ = [
    "AdvisoryPort",
    "AdvisoryResult",
    "AdvisoryStatus",
    "DependencyFinding",
    "DependencyScan",
    "run_dependency_scan",
]
