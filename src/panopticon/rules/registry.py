"""Deterministic decorator-based rule registry and execution boundary."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from panopticon.models.finding import Finding
from panopticon.rules.context import RuleContext

Severity = Literal["HIGH", "MEDIUM", "LOW", "INFO"]
Kind = Literal["confirmed", "review", "info"]
Line = Literal["config", "history", "observe", "static", "semantic", "dependency"]


@dataclass(frozen=True)
class RuleMeta:
    id: str
    severity: Severity | None
    kind: Kind
    line: Line
    fix_id: str | None = None
    since_version: str = "0.1"


RuleFn = Callable[[RuleContext], Iterable[Finding]]


@dataclass(frozen=True)
class RuleDiagnostic:
    rule_id: str
    code: str
    detail: str


@dataclass(frozen=True)
class Suppression:
    rule_id: str
    server_id: str
    reason: str
    expires_at: datetime | None = None

    def active(self, at: datetime) -> bool:
        if self.expires_at is None:
            return True
        if self.expires_at.tzinfo is None or at.tzinfo is None:
            return False
        return at < self.expires_at


_REGISTRY: dict[str, tuple[RuleMeta, RuleFn]] = {}


def rule(
    *,
    rule_id: str,
    severity: Severity | None,
    kind: Kind,
    line: Line,
    fix_id: str | None = None,
    since_version: str = "0.1",
) -> Callable[[RuleFn], RuleFn]:
    def deco(fn: RuleFn) -> RuleFn:
        if re.fullmatch(r"(CFG|HIST|WATCH|FIX|SENT)-\d{3}", rule_id) is None:
            raise ValueError(f"invalid rule id {rule_id}")
        if rule_id in _REGISTRY:
            raise ValueError(f"duplicate rule id {rule_id}")
        _REGISTRY[rule_id] = (
            RuleMeta(rule_id, severity, kind, line, fix_id, since_version),
            fn,
        )
        return fn

    return deco


def all_rules() -> dict[str, tuple[RuleMeta, RuleFn]]:
    return {key: _REGISTRY[key] for key in sorted(_REGISTRY)}


def run_rules(
    context: RuleContext,
    *,
    at: datetime,
    suppressions: Iterable[Suppression] = (),
    server_id: str | None = None,
) -> tuple[tuple[Finding, ...], tuple[RuleDiagnostic, ...]]:
    suppression_map = {(s.rule_id, s.server_id): s for s in suppressions if s.active(at)}
    findings: list[Finding] = []
    diagnostics: list[RuleDiagnostic] = []
    for rule_id, (_, fn) in all_rules().items():
        try:
            produced = fn(context)
            for finding in produced:
                suppression = suppression_map.get((rule_id, server_id or ""))
                if suppression is not None:
                    finding = finding.model_copy(update={"suppressed_by": suppression.reason})
                findings.append(finding)
        except Exception as exc:
            detail = type(exc).__name__
            diagnostics.append(RuleDiagnostic(rule_id, "RULE_EXCEPTION", detail))
    return tuple(findings), tuple(diagnostics)
