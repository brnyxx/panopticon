"""Adapters from scan findings to the bounded semantic reviewer."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from panopticon.analyzers.semantic.reviewer import (
    ReviewOutcome,
    SemanticStatus,
)
from panopticon.models.common import PersistedPath
from panopticon.models.finding import (
    EvidenceKind,
    Finding,
    FindingEvidence,
    FindingKind,
    FindingSeverity,
    SourceLocation,
)
from panopticon.models.ids import (
    FindingId,
    InstallationId,
    LogicalKey,
    ObservationId,
    ServerId,
)

from .scan import DeepDimension, DeepDimensionStatus, ScanFinding

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_INSTALLATION = InstallationId("inst_0000000000000000")


class SemanticReviewPort(Protocol):
    root: Path

    async def review(self, findings: tuple[Finding, ...]) -> ReviewOutcome: ...


def _severity(value: str) -> FindingSeverity:
    return {
        "CRITICAL": FindingSeverity.HIGH,
        "HIGH": FindingSeverity.HIGH,
        "MEDIUM": FindingSeverity.MEDIUM,
        "LOW": FindingSeverity.LOW,
    }.get(value.upper(), FindingSeverity.INFO)


def _id(prefix: str, finding: ScanFinding) -> str:
    payload = f"{prefix}\0{finding.rule_id}\0{finding.fingerprint}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _finding(value: ScanFinding) -> Finding:
    location = (
        SourceLocation(
            path=PersistedPath(value.path),
            line=value.line or 1,
            column=value.column or 1,
        )
        if value.path is not None
        else None
    )
    return Finding(
        schema_version="0.1",
        id=FindingId(_id("finding", value)),
        logical_key=LogicalKey(f"lk_{_id('logical', value)}"),
        rule_id=value.rule_id,
        severity=_severity(value.severity),
        kind=FindingKind.CONFIRMED,
        title=value.title,
        evidence=(
            FindingEvidence(
                kind=EvidenceKind.PATH,
                subject=value.rule_id,
                value=value.fingerprint,
            ),
        ),
        location=location,
        server_id=ServerId("local:scan"),
        installation_id=_INSTALLATION,
        observation_id=ObservationId("obs_scan"),
        span_ref=None,
        remediation_key=None,
        fix_available=False,
        declared_source=None,
        first_seen=_EPOCH,
        suppressed_by=None,
    )


class SemanticDeepPort:
    def __init__(self, reviewer: SemanticReviewPort) -> None:
        self.reviewer = reviewer

    def analyze(
        self,
        root: Path,
        findings: tuple[ScanFinding, ...],
    ) -> DeepDimension:
        if root != self.reviewer.root:
            return DeepDimension(
                DeepDimensionStatus.INCOMPLETE,
                "SEMANTIC_ROOT_MISMATCH",
            )
        candidates = tuple(_finding(item) for item in findings if item.rule_id.startswith("SENT-"))
        outcome = asyncio.run(self.reviewer.review(candidates))
        status = {
            SemanticStatus.COMPLETE: DeepDimensionStatus.COMPLETE,
            SemanticStatus.INCOMPLETE: DeepDimensionStatus.INCOMPLETE,
            SemanticStatus.UNSUPPORTED: DeepDimensionStatus.UNSUPPORTED,
        }[outcome.status]
        return DeepDimension(status, outcome.reason_code)


__all__ = ["SemanticDeepPort"]
