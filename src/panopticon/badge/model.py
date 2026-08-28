"""Immutable, sanitized values consumed by badge and evidence-card renderers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Literal

from panopticon.models.state import StageStatus


class DeclarationAuthority(StrEnum):
    AUTHORITATIVE = "AUTHORITATIVE"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


@dataclass(frozen=True, slots=True)
class CardStage:
    name: str
    status: StageStatus
    applicable: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, 40))


@dataclass(frozen=True, slots=True)
class CardFinding:
    rule_id: str
    kind: str = ""
    affects_eligibility: bool = True
    suppressed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _text(self.rule_id, 40))
        object.__setattr__(self, "kind", _text(self.kind, 40))


@dataclass(frozen=True, slots=True)
class EvidenceCardModel:
    server: str
    observed_on: date
    overall_coverage: StageStatus
    declaration_authority: DeclarationAuthority
    declaration_coverage: StageStatus
    stages: tuple[CardStage, ...] = ()
    uncovered_events: int = 0
    leaks: int = 0
    findings: tuple[CardFinding, ...] = ()
    locale: Literal["en", "ko"] = "en"
    excluded_evidence: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "server", _text(self.server, 200))
        object.__setattr__(self, "stages", tuple(self.stages))
        object.__setattr__(self, "findings", tuple(self.findings))
        counts = (self.uncovered_events, self.leaks, self.excluded_evidence)
        if any(count < 0 for count in counts):
            raise ValueError("counts must not be negative")


def _text(value: str, limit: int) -> str:
    if not value:
        raise ValueError("render values must be non-empty")
    if any(ord(character) < 32 for character in value):
        raise ValueError("control character in render value")
    return value[:limit]


def model_from(
    *,
    server: str,
    observed_on: date,
    overall_coverage: StageStatus,
    declaration_authority: DeclarationAuthority,
    declaration_coverage: StageStatus,
    stages: Iterable[CardStage] = (),
    uncovered_events: int = 0,
    leaks: int = 0,
    findings: Iterable[CardFinding] = (),
    locale: Literal["en", "ko"] = "en",
    excluded_evidence: int = 0,
) -> EvidenceCardModel:
    """Construct a bounded model from already-sanitized typed values."""
    return EvidenceCardModel(
        server=server,
        observed_on=observed_on,
        overall_coverage=overall_coverage,
        declaration_authority=declaration_authority,
        declaration_coverage=declaration_coverage,
        stages=tuple(stages),
        uncovered_events=uncovered_events,
        leaks=leaks,
        findings=tuple(findings),
        locale=locale,
        excluded_evidence=excluded_evidence,
    )


__all__ = [
    "CardFinding",
    "CardStage",
    "DeclarationAuthority",
    "EvidenceCardModel",
    "model_from",
]
