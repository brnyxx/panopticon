"""Typed boundary joining sanitized model and report findings."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from panopticon.models.finding import Finding
from panopticon.reporters.model import SanitizedRenderModel
from panopticon.util.leak_check import LeakContext, assert_clean

from .escaping import artifact_uri


@dataclass(frozen=True, slots=True)
class ReportFinding:
    rule_id: str
    title: str
    severity: str = "INFO"
    logical_key: str = ""
    path: str | None = None
    line: int | None = None
    column: int | None = None
    kind: str = "info"
    suppressed: bool = False
    fix_available: bool = False

    def __post_init__(self) -> None:
        if re.fullmatch(r"(?:CFG|HIST|WATCH|FIX|SENT)-\d{3}", self.rule_id) is None:
            raise ValueError("invalid report rule id")
        if self.severity not in {"HIGH", "MEDIUM", "LOW", "INFO"}:
            raise ValueError("invalid report severity")
        if not self.title:
            raise ValueError("report finding title must be non-empty")
        assert_clean(
            "\0".join((self.rule_id, self.title, self.logical_key, self.path or "")),
            LeakContext(),
        )
        if self.path is not None and artifact_uri(self.path) == "unknown":
            raise ValueError("report finding path must be repository-relative")


@dataclass(frozen=True, slots=True)
class ReportBundle:
    model: SanitizedRenderModel
    findings: tuple[ReportFinding, ...] = ()
    category: str = "panopticon"

    def __post_init__(self) -> None:
        if not self.category or len(self.category) > 128:
            raise ValueError("report category must be bounded and non-empty")


def _finding(value: Finding | ReportFinding) -> ReportFinding:
    if isinstance(value, ReportFinding):
        return value
    location = value.location
    return ReportFinding(
        rule_id=value.rule_id,
        title=value.title,
        severity=value.severity.value if value.severity is not None else "INFO",
        logical_key=str(value.logical_key),
        path=str(location.path) if location is not None else None,
        line=location.line if location is not None else None,
        column=location.column if location is not None else None,
        kind=value.kind.value,
        suppressed=value.suppressed_by is not None,
        fix_available=value.fix_available,
    )


def bundle(
    model: SanitizedRenderModel,
    findings: Iterable[Finding | ReportFinding] = (),
    *,
    category: str = "panopticon",
) -> ReportBundle:
    normalized = tuple(
        sorted(
            (_finding(finding) for finding in findings),
            key=lambda finding: (
                finding.rule_id,
                finding.logical_key,
                finding.path or "",
                finding.line or 0,
                finding.column or 0,
                finding.title,
            ),
        )
    )
    return ReportBundle(model, normalized, category)


__all__ = ["ReportBundle", "ReportFinding", "bundle"]
