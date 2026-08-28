# Copyright (c) 2026 MCP Sentinel contributors
# SPDX-License-Identifier: MIT
"""Deterministic static-analysis orchestration boundary."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from .catalog import RULE_IDS
from .model import RuleRunState, StaticAnalysisSummary, StaticContext, StaticScanResult
from .traversal import collect_static_files

STATIC_TIMEOUT_SECONDS = 120
Detector = Callable[[StaticContext, RuleRunState], None]


def select_rule_ids(tokens: tuple[str, ...]) -> tuple[str, ...]:
    includes = {token.removeprefix("+") for token in tokens if not token.startswith("-")}
    excludes = {token.removeprefix("-") for token in tokens if token.startswith("-")}
    selected = includes if includes else set(RULE_IDS)
    return tuple(rule_id for rule_id in RULE_IDS if rule_id in selected - excludes)


def run_static_scan(
    configuration: object, scan_id: object = None, *, timestamp: object = None
) -> StaticScanResult:
    """Collect files and invoke registered product detectors without target execution.

    Detector discovery is optional so the core remains importable while sibling ports land.
    """
    del scan_id, timestamp
    started = time.monotonic()
    scanner = getattr(configuration, "scanner", None)
    tokens = tuple(getattr(scanner, "rules", ()))
    ignore_paths = tuple(getattr(scanner, "ignore_paths", ()))
    root = Path(configuration.scan_root)
    files = collect_static_files(root, ignore_paths)
    context = StaticContext(configuration, files)
    selected = select_rule_ids(tokens)
    states = {rule_id: RuleRunState() for rule_id in selected}
    detectors = _load_detectors()
    for rule_id in selected:
        if time.monotonic() - started > STATIC_TIMEOUT_SECONDS:
            raise TimeoutError("static analysis exceeded timeout")
        detector = detectors.get(rule_id)
        if detector is not None:
            detector(context, states[rule_id])
    total = sum(len(state.matches) for state in states.values())
    summary = StaticAnalysisSummary(
        selected,
        files.scanned_file_count,
        files.ignored_file_count,
        total,
        round((time.monotonic() - started) * 1000),
    )
    return StaticScanResult(tuple(), files.warnings, summary)


def _load_detectors() -> dict[str, Detector]:
    detectors: dict[str, Detector] = {}
    for rule_id in ("SENT-001", "SENT-003", "SENT-004", "SENT-006", "SENT-007"):
        try:
            module = __import__(
                f"panopticon.analyzers.static.rules.sent{rule_id[-3:]}", fromlist=["detect"]
            )
            detector = getattr(module, "detect", None)
            if callable(detector):
                detectors[rule_id] = detector
        except ImportError:
            continue
    return detectors
