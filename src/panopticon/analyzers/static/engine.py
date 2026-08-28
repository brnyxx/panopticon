# Copyright (c) 2026 MCP Sentinel contributors
# SPDX-License-Identifier: MIT
"""Deterministic static-analysis orchestration boundary."""

from __future__ import annotations

import time
from collections.abc import Callable

from .catalog import RULE_IDS
from .model import (
    RuleRunState,
    StaticAnalysisSummary,
    StaticConfiguration,
    StaticContext,
    StaticMatch,
    StaticScanResult,
)
from .rules import sent001, sent003, sent004, sent006, sent007
from .traversal import collect_static_files

STATIC_TIMEOUT_SECONDS = 120
Detector = Callable[[StaticContext, RuleRunState], None]
_DETECTORS: dict[str, Detector] = {
    "SENT-001": sent001.detect,
    "SENT-003": sent003.detect,
    "SENT-004": sent004.detect,
    "SENT-006": sent006.detect,
    "SENT-007": sent007.detect,
}


def select_rule_ids(tokens: tuple[str, ...]) -> tuple[str, ...]:
    includes = {token.removeprefix("+") for token in tokens if not token.startswith("-")}
    excludes = {token.removeprefix("-") for token in tokens if token.startswith("-")}
    selected = includes if includes else set(RULE_IDS)
    return tuple(rule_id for rule_id in RULE_IDS if rule_id in selected - excludes)


def run_static_scan(configuration: StaticConfiguration) -> StaticScanResult:
    started = time.monotonic()
    scanner = configuration.scanner
    files = collect_static_files(configuration.scan_root, scanner.ignore_paths)
    context = StaticContext(configuration, files)
    selected = select_rule_ids(scanner.selected_rule_ids)
    states = {rule_id: RuleRunState() for rule_id in selected}
    for rule_id in selected:
        if time.monotonic() - started > STATIC_TIMEOUT_SECONDS:
            raise TimeoutError("static analysis exceeded timeout")
        detector = _DETECTORS.get(rule_id)
        if detector is not None:
            detector(context, states[rule_id])
    matches = tuple(
        sorted(
            (match for rule_id in selected for match in states[rule_id].matches),
            key=_match_key,
        )
    )
    summary = StaticAnalysisSummary(
        selected,
        files.scanned_file_count,
        files.ignored_file_count,
        len(matches),
        round((time.monotonic() - started) * 1000),
    )
    return StaticScanResult(matches, files.warnings, summary)


def _match_key(match: StaticMatch) -> tuple[str, str, int, int]:
    return (
        match.rule_id,
        match.path,
        match.range.start_line,
        match.range.start_column,
    )
