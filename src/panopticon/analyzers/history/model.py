"""Strict contracts for normalized registry history analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from panopticon.models.ids import InstallationId, ObservationId, ServerId
from panopticon.registry.history import SnapshotSeries


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


@dataclass(frozen=True, slots=True)
class HistoryRuleInput:
    series: SnapshotSeries
    server_id: ServerId
    installation_id: InstallationId
    observation_id: ObservationId
    observed_at: datetime

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
