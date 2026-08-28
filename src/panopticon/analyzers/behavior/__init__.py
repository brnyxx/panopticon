"""WATCH-* rules (panopticon-buildplan.md §20.3)."""

from .catalog import RULE_CATALOG, RULE_IDS
from .model import (
    Authority,
    BehaviorInput,
    CoverageState,
    DeclaredAuthority,
    EvidenceKind,
    OutcomeState,
    WatchEvidence,
    WatchMatch,
)
from .registry_rules import register_rules
from .rules import evaluate, evaluate_rule

register_rules()

__all__ = [
    "RULE_CATALOG",
    "RULE_IDS",
    "Authority",
    "BehaviorInput",
    "CoverageState",
    "DeclaredAuthority",
    "EvidenceKind",
    "OutcomeState",
    "WatchEvidence",
    "WatchMatch",
    "evaluate",
    "evaluate_rule",
    "register_rules",
]
