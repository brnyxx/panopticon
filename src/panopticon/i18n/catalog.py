"""Deterministic catalog of observable and explain-only rule metadata."""

from __future__ import annotations

from dataclasses import dataclass

from panopticon.analyzers.behavior.catalog import RULE_CATALOG as WATCH_RULES
from panopticon.analyzers.behavior.model import WatchRule
from panopticon.analyzers.config.catalog import RULE_CATALOG as CFG_RULES
from panopticon.analyzers.config.model import ConfigRule
from panopticon.analyzers.history.catalog import RULES as HIST_RULES
from panopticon.analyzers.history.model import HistoryRule
from panopticon.analyzers.static.catalog import RULES as STATIC_RULES
from panopticon.analyzers.static.model import RuleDefinition
from panopticon.fix.rules import RULES as FIX_RULES
from panopticon.fix.rules import FixRule


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    rule_id: str
    line: str
    severity: str
    kind: str
    fix_id: str | None = None
    title: str = ""


def _config(rule: ConfigRule) -> CatalogEntry:
    return CatalogEntry(
        rule.rule_id,
        "observe",
        rule.severity.value,
        rule.kind.value,
        rule.fix_id,
        rule.condition,
    )


def _history(rule: HistoryRule) -> CatalogEntry:
    return CatalogEntry(
        rule.rule_id,
        "observe",
        rule.severity.value,
        rule.kind.value,
        rule.fix_id,
        rule.condition,
    )


def _watch(rule: WatchRule) -> CatalogEntry:
    return CatalogEntry(
        rule.rule_id,
        "observe",
        rule.severity,
        rule.kind,
        None,
        rule.condition,
    )


def _fix(rule: FixRule) -> CatalogEntry:
    return CatalogEntry(rule.fix_id, "fix", "", "remediation")


def _static(rule: RuleDefinition) -> CatalogEntry:
    return CatalogEntry(
        rule.rule_id,
        "analyze",
        rule.impact.value,
        rule.engine.value,
        None,
        rule.title,
    )


OBSERVATION_CATALOG = (
    *(_config(rule) for rule in CFG_RULES),
    *(_history(rule) for rule in HIST_RULES),
    *(_watch(rule) for rule in WATCH_RULES),
)
FIX_METADATA = tuple(_fix(rule) for rule in FIX_RULES)
_STATIC_METADATA = tuple(_static(rule) for rule in STATIC_RULES)
_DYNAMIC_TITLES = {
    "SENT-008": "Out-of-scope tool execution",
    "SENT-009": "Oversized argument accepted",
    "SENT-010": "Injection payload executed",
    "SENT-011": "Malformed schema input processed",
}
DYNAMIC_METADATA = tuple(
    CatalogEntry(rule_id, "analyze", "", "dynamic", None, title)
    for rule_id, title in _DYNAMIC_TITLES.items()
)
SENT_METADATA = (*_STATIC_METADATA, *DYNAMIC_METADATA)
CATALOG = tuple(
    sorted(
        (*OBSERVATION_CATALOG, *FIX_METADATA, *SENT_METADATA),
        key=lambda entry: entry.rule_id,
    )
)
RULE_IDS = tuple(entry.rule_id for entry in CATALOG)
OBSERVATION_RULE_IDS = tuple(entry.rule_id for entry in OBSERVATION_CATALOG)
BY_ID = {entry.rule_id: entry for entry in CATALOG}


__all__ = [
    "BY_ID",
    "CATALOG",
    "DYNAMIC_METADATA",
    "FIX_METADATA",
    "OBSERVATION_CATALOG",
    "OBSERVATION_RULE_IDS",
    "RULE_IDS",
    "SENT_METADATA",
    "CatalogEntry",
]
