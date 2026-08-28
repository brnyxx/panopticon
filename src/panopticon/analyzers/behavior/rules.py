"""Executable deterministic WATCH rule evaluation."""

from __future__ import annotations

from collections.abc import Callable

from ._rules_behavior import (
    rule001,
    rule002,
    rule006,
    rule008,
    rule009,
    rule010,
    rule011,
    rule013,
)
from ._rules_network import rule003, rule004, rule005, rule007, rule012, rule014
from .catalog import RULE_CATALOG
from .model import BehaviorInput, WatchMatch

_HANDLERS: tuple[Callable[[BehaviorInput], WatchMatch], ...] = (
    rule001,
    rule002,
    rule003,
    rule004,
    rule005,
    rule006,
    rule007,
    rule008,
    rule009,
    rule010,
    rule011,
    rule012,
    rule013,
    rule014,
)


def evaluate(context: BehaviorInput) -> tuple[WatchMatch, ...]:
    """Evaluate all rules in catalog order without hiding absent-source uncertainty."""
    return tuple(handler(context) for handler in _HANDLERS)


def evaluate_rule(rule_id: str, context: BehaviorInput) -> WatchMatch:
    index = next((i for i, rule in enumerate(RULE_CATALOG) if rule.rule_id == rule_id), -1)
    if index < 0:
        raise KeyError(rule_id)
    return _HANDLERS[index](context)


__all__ = ["evaluate", "evaluate_rule"]
