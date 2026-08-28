"""Typed deterministic finding views for static analyzer matches."""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import RULE_BY_ID
from .model import StaticMatch


@dataclass(frozen=True, slots=True)
class StaticFindingView:
    rule_id: str
    title: str
    severity: str
    fingerprint: str
    path: str
    line: int
    column: int
    kind: str = "confirmed"


def finding_views(matches: tuple[StaticMatch, ...]) -> tuple[StaticFindingView, ...]:
    findings = tuple(
        StaticFindingView(
            rule_id=match.rule_id,
            title=RULE_BY_ID[match.rule_id].title,
            severity=RULE_BY_ID[match.rule_id].impact.value,
            fingerprint=(
                match.fingerprint
                or (
                    f"{match.rule_id}:{match.path}:"
                    f"{match.range.start_line}:{match.range.start_column}"
                )
            ),
            path=match.path,
            line=match.range.start_line,
            column=match.range.start_column,
        )
        for match in matches
    )
    return tuple(
        sorted(
            findings,
            key=lambda finding: (
                finding.rule_id,
                finding.path,
                finding.line,
                finding.column,
            ),
        )
    )


__all__ = ["StaticFindingView", "finding_views"]
