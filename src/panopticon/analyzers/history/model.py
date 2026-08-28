"""Strict contracts for normalized registry history analysis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class HistorySeverity(StrEnum):
    INFO = "INFO"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class HistoryKind(StrEnum):
    INFO = "info"
    REVIEW = "review"


class HistoryStatus(StrEnum):
    FINDING = "finding"
    CLEAR = "clear"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class HistoryEvidence:
    subject: str
    classification: str


@dataclass(frozen=True, slots=True)
class HistoryOutcome:
    rule_id: str
    status: HistoryStatus
    severity: HistorySeverity
    kind: HistoryKind
    fix_id: str | None
    reason: str
    evidence: tuple[HistoryEvidence, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoryRule:
    rule_id: str
    severity: HistorySeverity
    kind: HistoryKind
    fix_id: str | None
    condition: str
