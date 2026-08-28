"""HIST-* normalized registry history analyzer."""

from .catalog import RULE_BY_ID, RULE_IDS, RULES
from .model import (
    HistoryEvidence,
    HistoryKind,
    HistoryOutcome,
    HistoryRule,
    HistorySeverity,
    HistoryStatus,
)
from .rules import analyze_history, evaluate_rule

__all__ = [
    "RULES",
    "RULE_BY_ID",
    "RULE_IDS",
    "HistoryEvidence",
    "HistoryKind",
    "HistoryOutcome",
    "HistoryRule",
    "HistorySeverity",
    "HistoryStatus",
    "analyze_history",
    "evaluate_rule",
]
