# Copyright (c) 2026 MCP Sentinel contributors
# SPDX-License-Identifier: MIT
"""SENT-002 Semgrep result adapter."""

from panopticon.analyzers.static.model import RuleRunState, StaticMatch


def run(matches: list[StaticMatch], state: RuleRunState) -> None:
    state.matches.extend(matches)
