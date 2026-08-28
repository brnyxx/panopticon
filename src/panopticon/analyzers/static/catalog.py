# Copyright (c) 2026 MCP Sentinel contributors
# SPDX-License-Identifier: MIT
"""Authoritative static rule metadata."""

from .model import Impact, RuleDefinition, RuleEngine

_DOC_ROOT = "https://github.com/BashaarJavaid/MCP-Sentinel/blob/main/docs/rules.md"


def _rule(
    rule_id: str,
    title: str,
    description: str,
    impact: Impact,
    remediation: str,
    risk: str,
    engine: RuleEngine,
) -> RuleDefinition:
    return RuleDefinition(
        rule_id,
        title,
        description,
        impact,
        remediation,
        risk,
        "",
        engine,
        f"{_DOC_ROOT}#{rule_id.lower()}",
    )


RULES = tuple(
    _rule(*args)
    for args in (
        (
            "SENT-001",
            "Overly broad tool permission scope",
            "The tool declares filesystem or network access broader than its handler uses.",
            Impact.HIGH,
            "Narrow each declared scope to the resources the handler actually requires.",
            "Medium",
            RuleEngine.AST,
        ),
        (
            "SENT-002",
            "Unsafe execution from tool input",
            "Tool-controlled input reaches an unsafe execution or deserialization sink.",
            Impact.CRITICAL,
            "Replace dynamic execution with explicit parsers and fixed command allowlists.",
            "Low",
            RuleEngine.SEMGREP,
        ),
        (
            "SENT-003",
            "Missing tool input validation",
            "A tool handler consumes parameters before framework or explicit validation.",
            Impact.MEDIUM,
            "Use concrete handler types, Pydantic models, or JSON Schema before first use.",
            "Medium",
            RuleEngine.AST,
        ),
        (
            "SENT-004",
            "Unsanitized tool content in prompt",
            (
                "Tool output or description flows into a later model prompt "
                "without a trusted sanitizer."
            ),
            Impact.HIGH,
            "Pass tool-controlled text through a configured sanitizer before prompt construction.",
            "Medium-High",
            RuleEngine.AST,
        ),
        (
            "SENT-005",
            "Hardcoded secret",
            (
                "Source or configuration contains a credential signature "
                "or contextual high-entropy secret."
            ),
            Impact.CRITICAL,
            "Load credentials from an external secret store or environment at runtime.",
            "Low-Medium",
            RuleEngine.SEMGREP,
        ),
        (
            "SENT-006",
            "Missing or ineffective route authentication",
            "An HTTP route lacks inherited authentication or uses a no-op verifier.",
            Impact.HIGH,
            (
                "Require credential verification and an explicit rejection path "
                "before route execution."
            ),
            "Low",
            RuleEngine.AST,
        ),
        (
            "SENT-007",
            "Unverified tool manifest",
            "Manifest bytes reach registration without a trusted hash or signature verification.",
            Impact.MEDIUM,
            "Verify a pinned SHA-256 digest or trusted detached signature before parsing and use.",
            "Low",
            RuleEngine.AST,
        ),
    )
)
RULE_BY_ID = {rule.rule_id: rule for rule in RULES}
RULE_IDS = tuple(rule.rule_id for rule in RULES)
