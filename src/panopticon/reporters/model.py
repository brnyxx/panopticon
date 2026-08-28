"""Immutable sanitized values shared by output reporters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from panopticon.engine.contracts import Result
from panopticon.util.leak_check import LeakContext, find_leaks


@dataclass(frozen=True, slots=True)
class StageView:
    name: str
    status: str
    reason_code: str
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SanitizedRenderModel:
    status: str
    reason_code: str
    stages: tuple[StageView, ...] = ()
    diagnostics: tuple[str, ...] = ()
    evidence_count: int = 0
    excluded_allowlist_count: int = 0
    suppression_count: int = 0


def from_result(result: Result, *, context: LeakContext | None = None) -> SanitizedRenderModel:
    """Copy only typed scalar values from an engine result, rejecting raw leaks."""
    leak_context = context or LeakContext(home_paths=(str(Path.home()),))
    if find_leaks(repr(result), leak_context):
        raise ValueError("report input contains prohibited evidence")
    coverage = result.coverage
    stages = tuple(
        StageView(
            name,
            stage.status.value,
            stage.reason_code.value,
            tuple(diagnostic.code for diagnostic in stage.diagnostics),
        )
        for name, stage in (
            ("file", coverage.file),
            ("net", coverage.net),
            ("process", coverage.process),
            ("dns", coverage.dns),
            ("proxy", coverage.proxy),
            ("snapshot", coverage.snapshot),
            ("stdio", coverage.stdio),
        )
    )
    return SanitizedRenderModel(
        status=result.status.value,
        reason_code=result.reason_code.value,
        stages=stages,
        diagnostics=tuple(diagnostic.code for diagnostic in result.diagnostics),
    )


sanitize = from_result

__all__ = ["SanitizedRenderModel", "StageView", "from_result", "sanitize"]
