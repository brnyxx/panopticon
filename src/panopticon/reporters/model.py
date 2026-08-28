"""Immutable, sanitized values shared by output reporters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    excluded_count: int = 0
    suppressed_count: int = 0
    excluded_allowlist_count: int = 0
    suppression_count: int = 0


def _text(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def from_result(result: Result, *, context: LeakContext | None = None) -> SanitizedRenderModel:
    """Copy only typed scalar values from an engine result, rejecting leaks."""
    stages: list[StageView] = []
    coverage = getattr(result, "coverage", None)
    if coverage is not None:
        for name in ("file", "net", "process", "dns", "proxy", "snapshot", "stdio"):
            stage = getattr(coverage, name, None)
            if stage is None:
                continue
            stages.append(
                StageView(
                    name,
                    _text(stage.status),
                    _text(stage.reason_code),
                    tuple(d.code for d in stage.diagnostics),
                )
            )
    diagnostics = tuple(d.code for d in getattr(result, "diagnostics", ()))
    model = SanitizedRenderModel(
        status=_text(result.status),
        reason_code=_text(result.reason_code),
        stages=tuple(stages),
        diagnostics=diagnostics,
        evidence_count=int(getattr(result, "evidence_count", 0)),
        excluded_count=int(getattr(result, "excluded_count", 0)),
        suppressed_count=int(getattr(result, "suppressed_count", 0)),
        excluded_allowlist_count=int(
            getattr(result, "excluded_allowlist_count", getattr(result, "excluded_count", 0))
        ),
        suppression_count=int(
            getattr(result, "suppression_count", getattr(result, "suppressed_count", 0))
        ),
    )
    raw = repr(result)
    if hasattr(result, "__dict__"):
        raw += repr(vars(result))
    if find_leaks(raw, context or LeakContext(home_paths=(str(Path.home()),))):
        raise ValueError("report input contains prohibited evidence")
    return model


sanitize = from_result


__all__ = ["SanitizedRenderModel", "StageView", "from_result", "sanitize"]
