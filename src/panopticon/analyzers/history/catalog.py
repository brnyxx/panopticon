"""Authoritative HIST rule metadata in stable order."""

from __future__ import annotations

from .model import HistoryKind, HistoryRule, HistorySeverity

RULES: tuple[HistoryRule, ...] = (
    HistoryRule(
        "HIST-001",
        HistorySeverity.INFO,
        HistoryKind.INFO,
        None,
        "one or more non-yanked releases since baseline",
    ),
    HistoryRule(
        "HIST-002",
        HistorySeverity.MEDIUM,
        HistoryKind.INFO,
        None,
        "major version jump since baseline",
    ),
    HistoryRule(
        "HIST-003",
        HistorySeverity.HIGH,
        HistoryKind.REVIEW,
        None,
        "npm maintainers changed since baseline",
    ),
    HistoryRule(
        "HIST-004",
        HistorySeverity.MEDIUM,
        HistoryKind.INFO,
        None,
        "repository archived or inactive for at least twelve months",
    ),
)
RULE_BY_ID = {rule.rule_id: rule for rule in RULES}
RULE_IDS = tuple(rule.rule_id for rule in RULES)
