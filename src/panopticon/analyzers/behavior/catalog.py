"""Exact WATCH-001..014 metadata from buildplan §20.3."""

from __future__ import annotations

from .model import WatchRule

RULE_CATALOG: tuple[WatchRule, ...] = (
    WatchRule(
        "WATCH-001",
        "HIGH",
        "confirmed",
        "decoy value exfiltrated via network, file, process arg, or stderr",
    ),
    WatchRule("WATCH-002", "HIGH", "confirmed", "credential decoy file read without declaration"),
    WatchRule(
        "WATCH-003", "MEDIUM", "confirmed", "connection to undeclared host (allowlist excluded)"
    ),
    WatchRule("WATCH-004", "MEDIUM", "confirmed", "network activity in __idle__ span"),
    WatchRule("WATCH-005", "MEDIUM", "confirmed", "non-registry host during __install__"),
    WatchRule("WATCH-006", "LOW", "review", "personal config file read without declaration"),
    WatchRule("WATCH-007", "MEDIUM", "confirmed", "proxy bypass attempt (DROP)"),
    WatchRule(
        "WATCH-008",
        "MEDIUM",
        "confirmed",
        "undeclared external process (interpreters, git, npm, uv excluded)",
    ),
    WatchRule(
        "WATCH-009",
        "LOW",
        "info",
        "broad enumeration (≥10 stat/read under Documents/Desktop/Downloads)",
    ),
    WatchRule(
        "WATCH-010",
        "INFO",
        "info",
        "declared = observed (badge condition; requires declared COMPLETE)",
    ),
    WatchRule("WATCH-011", "—", "review", "verdict withheld because declared is NONE/PARTIAL"),
    WatchRule("WATCH-012", "INFO", "info", "remote response contains many external URLs"),
    WatchRule(
        "WATCH-013",
        "MEDIUM",
        "confirmed",
        "tool declared readOnlyHint: true performs a write or network POST",
    ),
    WatchRule(
        "WATCH-014",
        "MEDIUM",
        "confirmed",
        "network activity in __startup__ span (pre-handshake beacon)",
    ),
)
RULE_BY_ID = {rule.rule_id: rule for rule in RULE_CATALOG}
RULE_IDS = tuple(rule.rule_id for rule in RULE_CATALOG)
