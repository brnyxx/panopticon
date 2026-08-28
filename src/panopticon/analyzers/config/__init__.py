"""Typed CFG-001..012 configuration analyzer."""

from .catalog import FILESYSTEM_MCP_IDENTIFIERS, RULE_BY_ID, RULE_CATALOG, RULE_IDS
from .model import ConfigEvidence, ConfigInput, ConfigKind, ConfigMatch, ConfigRule, ConfigSeverity
from .rules import analyze

__all__ = [
    "FILESYSTEM_MCP_IDENTIFIERS",
    "RULE_BY_ID",
    "RULE_CATALOG",
    "RULE_IDS",
    "ConfigEvidence",
    "ConfigInput",
    "ConfigKind",
    "ConfigMatch",
    "ConfigRule",
    "ConfigSeverity",
    "analyze",
]
