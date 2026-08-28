# Copyright (c) 2026 MCP Sentinel contributors
# SPDX-License-Identifier: MIT
"""Strict typed contracts for deterministic static analysis."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Impact(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RuleEngine(StrEnum):
    AST = "ast"
    SEMGREP = "semgrep"


@dataclass(frozen=True, slots=True)
class SourceRange:
    start_line: int
    start_column: int
    end_line: int
    end_column: int


@dataclass(frozen=True, slots=True)
class ReportWarning:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    rule_id: str
    title: str
    description: str
    impact: Impact
    remediation: str
    false_positive_risk: str
    owasp_category: str
    engine: RuleEngine
    help_uri: str


@dataclass(frozen=True, slots=True)
class StaticMatch:
    rule_id: str
    path: str
    range: SourceRange
    snippet: str
    fingerprint: str | None = None
    match_kinds: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ParsedPythonFile:
    path: Path
    relative_path: str
    source: str
    tree: ast.Module


@dataclass(frozen=True, slots=True)
class StaticFileSet:
    python_files: tuple[ParsedPythonFile, ...]
    config_files: tuple[Path, ...]
    scanned_file_count: int
    ignored_file_count: int
    warnings: tuple[ReportWarning, ...]


@dataclass
class RuleRunState:
    matches: list[StaticMatch] = field(default_factory=list)
    exemptions: dict[str, int] = field(default_factory=dict)
    skip_reason: str | None = None

    def exempt(self, reason: str) -> None:
        self.exemptions[reason] = self.exemptions.get(reason, 0) + 1


@dataclass(frozen=True, slots=True)
class SecretAllowlistEntry:
    path: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class StaticRuleOptions:
    sanitizers: tuple[str, ...] = ()
    secret_allowlist: tuple[SecretAllowlistEntry, ...] = ()
    public_routes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScannerConfig:
    selected_rule_ids: tuple[str, ...] = ()
    ignore_paths: tuple[str, ...] = ()
    rule_options: StaticRuleOptions = StaticRuleOptions()


@dataclass(frozen=True, slots=True)
class StaticConfiguration:
    scan_root: Path
    scanner: ScannerConfig


@dataclass(frozen=True, slots=True)
class StaticContext:
    configuration: StaticConfiguration
    files: StaticFileSet


@dataclass(frozen=True, slots=True)
class StaticAnalysisSummary:
    selected_rule_ids: tuple[str, ...]
    scanned_file_count: int
    ignored_file_count: int
    total_matches: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class StaticScanResult:
    matches: tuple[StaticMatch, ...]
    warnings: tuple[ReportWarning, ...]
    summary: StaticAnalysisSummary
