"""Decorator-based rule registry. See panopticon-buildplan.md §14.

    @rule(id="WATCH-001", severity="HIGH", kind="confirmed", line="observe")
    def decoy_leak(ctx: RuleContext) -> Iterable[Finding]: ...

`scripts/check_rules.py` asserts every registered rule has fixtures and ko/en explain docs.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

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


RuleFn = Callable[[Any], Iterable[Any]]

_REGISTRY: dict[str, tuple[RuleMeta, RuleFn]] = {}


def rule(
    *,
    id: str,  # noqa: A002
    severity: Severity | None,
    kind: Kind,
    line: Line,
    fix_id: str | None = None,
    since_version: str = "0.1",
) -> Callable[[RuleFn], RuleFn]:
    def deco(fn: RuleFn) -> RuleFn:
        if id in _REGISTRY:
            raise ValueError(f"duplicate rule id {id}")
        _REGISTRY[id] = (RuleMeta(id, severity, kind, line, fix_id, since_version), fn)
        return fn

    return deco


def all_rules() -> dict[str, tuple[RuleMeta, RuleFn]]:
    return dict(_REGISTRY)
