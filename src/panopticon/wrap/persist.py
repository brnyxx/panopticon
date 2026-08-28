"""Typed conversion and leak-checked persistence for wrap records."""

from __future__ import annotations

import hashlib

from panopticon.models.artifacts import WrapRecord, WrapSpan
from panopticon.models.ids import InstallationId, ServerId, SpanId
from panopticon.models.state import (
    CompleteStage,
    NotRequestedStage,
    PartialStage,
    ReasonCode,
    StageStatus,
)
from panopticon.models.state import (
    Coverage as PersistedCoverage,
)
from panopticon.store.contracts import PersistResult
from panopticon.store.repository import ArtifactRepository

from .model import Coverage, WrapRecordCandidate


def _span_id(candidate: WrapRecordCandidate) -> SpanId:
    raw = "\0".join(
        (
            candidate.installation_id,
            candidate.span.tool,
            candidate.span.request_id,
            candidate.span.started_at.isoformat(),
        )
    )
    digest = hashlib.sha256(raw.encode()).hexdigest()[:15]
    return SpanId(f"wrap:{int(digest, 16)}")


def _coverage(candidate: WrapRecordCandidate) -> PersistedCoverage:
    not_requested = NotRequestedStage(
        status=StageStatus.NOT_REQUESTED,
        reason_code=ReasonCode.NOT_APPLICABLE,
        diagnostics=(),
    )
    stdio = (
        CompleteStage(
            status=StageStatus.COMPLETE,
            reason_code=ReasonCode.COMPLETED,
            diagnostics=(),
        )
        if candidate.coverage is Coverage.COMPLETE
        else PartialStage(
            status=StageStatus.PARTIAL,
            reason_code=ReasonCode.PARTIAL_COVERAGE,
            diagnostics=(),
        )
    )
    return PersistedCoverage(
        file=not_requested,
        net=not_requested,
        process=not_requested,
        dns=not_requested,
        proxy=not_requested,
        snapshot=not_requested,
        stdio=stdio,
    )


def to_record(candidate: WrapRecordCandidate) -> WrapRecord:
    return WrapRecord(
        schema_version="1.0",
        ts=candidate.span.finished_at,
        server_id=ServerId(candidate.server_id),
        installation_id=InstallationId(candidate.installation_id),
        span=WrapSpan(
            span_id=_span_id(candidate),
            tool=candidate.span.tool,
            request_id=candidate.span.request_id,
            duration_ms=candidate.span.duration_ms,
        ),
        events=candidate.events,
        coverage=_coverage(candidate),
    )


def persist_record(
    repository: ArtifactRepository,
    candidate: WrapRecordCandidate,
) -> PersistResult:
    return repository.persist_wrap_record(to_record(candidate))


__all__ = ["persist_record", "to_record"]
