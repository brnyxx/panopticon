# Copyright (c) 2026 MCP Sentinel contributors
# SPDX-License-Identifier: MIT
"""Typed dependency-input outcomes adapted from pinned MCP-Sentinel logic."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DependencyStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNSUPPORTED = "UNSUPPORTED"


class DependencyReason(StrEnum):
    COMPLETED = "COMPLETED"
    INPUT_MISSING = "INPUT_MISSING"
    INPUT_AMBIGUOUS = "INPUT_AMBIGUOUS"
    INPUT_INVALID = "INPUT_INVALID"
    INSTALL_SHAPE_UNSUPPORTED = "INSTALL_SHAPE_UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class RequirementRecord:
    name: str
    specifier: str
    marker: str | None = None


@dataclass(frozen=True, slots=True)
class DependencyInput:
    status: DependencyStatus
    reason_code: DependencyReason
    requirements: tuple[RequirementRecord, ...] = ()
    source_paths: tuple[str, ...] = ()
    fingerprint: str | None = None
    diagnostics: tuple[str, ...] = ()
