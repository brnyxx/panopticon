"""Typed CFG-001..012 configuration analyzer."""

from .catalog import FILESYSTEM_MCP_IDENTIFIERS, RULE_BY_ID, RULE_CATALOG, RULE_IDS
from .model import ConfigEvidence, ConfigInput, ConfigKind, ConfigMatch, ConfigRule, ConfigSeverity
from .registry_rules import register_rules
from .rules import analyze

register_rules()

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
