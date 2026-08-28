"""HIST-* normalized registry history analyzer."""

from .catalog import RULE_BY_ID, RULE_IDS, RULES
from .model import (
    HistoryEvidence,
    HistoryKind,
    HistoryOutcome,
    HistoryRule,
    HistoryRuleInput,
    HistorySeverity,
    HistoryStatus,
)
from .registry_rules import register_rules
from .rules import analyze_history, evaluate_rule

register_rules()

__all__ = [
    "RULES",
    "RULE_BY_ID",
    "RULE_IDS",
    "HistoryEvidence",
    "HistoryKind",
    "HistoryOutcome",
    "HistoryRule",
    "HistoryRuleInput",
    "HistorySeverity",
    "HistoryStatus",
    "analyze_history",
    "evaluate_rule",
]
