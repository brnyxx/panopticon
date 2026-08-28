"""Machine-consumed CFG rule metadata (buildplan §20.1)."""

from __future__ import annotations

from .model import ConfigKind, ConfigRule, ConfigSeverity

FILESYSTEM_MCP_IDENTIFIERS: tuple[str, ...] = (
    "filesystem",
    "@modelcontextprotocol/server-filesystem",
)

RULE_CATALOG: tuple[ConfigRule, ...] = (
    ConfigRule(
        "CFG-001",
        ConfigSeverity.HIGH,
        ConfigKind.CONFIRMED,
        "FIX-001",
        "known token pattern in environment value",
    ),
    ConfigRule(
        "CFG-002",
        ConfigSeverity.MEDIUM,
        ConfigKind.CONFIRMED,
        "FIX-002",
        "package version is unpinned",
    ),
    ConfigRule("CFG-003", ConfigSeverity.MEDIUM, ConfigKind.REVIEW, None, "shell command shape"),
    ConfigRule(
        "CFG-004",
        ConfigSeverity.HIGH,
        ConfigKind.CONFIRMED,
        "FIX-004",
        "broad path on filesystem MCP",
    ),
    ConfigRule(
        "CFG-005",
        ConfigSeverity.LOW,
        ConfigKind.INFO,
        "FIX-005",
        "duplicate server version mismatch",
    ),
    ConfigRule(
        "CFG-006", ConfigSeverity.MEDIUM, ConfigKind.REVIEW, None, "unverifiable package source"
    ),
    ConfigRule(
        "CFG-007",
        ConfigSeverity.LOW,
        ConfigKind.REVIEW,
        "FIX-001",
        "high entropy environment value",
    ),
    ConfigRule(
        "CFG-008", ConfigSeverity.MEDIUM, ConfigKind.CONFIRMED, "FIX-008", "plaintext remote URL"
    ),
    ConfigRule("CFG-009", ConfigSeverity.INFO, ConfigKind.INFO, "FIX-010", "server disabled"),
    ConfigRule(
        "CFG-010", ConfigSeverity.MEDIUM, ConfigKind.REVIEW, None, "absolute system argument"
    ),
    ConfigRule(
        "CFG-011", ConfigSeverity.LOW, ConfigKind.REVIEW, "FIX-001", "token-shaped remote header"
    ),
    ConfigRule("CFG-012", ConfigSeverity.INFO, ConfigKind.INFO, None, "stdio server not wrapped"),
)
RULE_BY_ID = {rule.rule_id: rule for rule in RULE_CATALOG}
RULE_IDS = tuple(rule.rule_id for rule in RULE_CATALOG)
