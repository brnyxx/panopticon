"""Exhaustive mapping from local-watch coverage to persisted stage state."""

from __future__ import annotations

from panopticon.models.observation import DeclaredCompleteness
from panopticon.models.state import (
    CompleteStage,
    Coverage,
    IncompleteStage,
    NotRequestedStage,
    ObservationState,
    PartialStage,
    ReasonCode,
    StageResult,
    StageSet,
    StageStatus,
    UnsupportedStage,
)
from panopticon.probe.protocol import ProtocolEra

from .watch_local_model import LocalWatchResult, LocalWatchStatus
from .watch_model import Coverage as WatchCoverage


def _complete(reason: ReasonCode = ReasonCode.COMPLETED) -> StageResult:
    if reason is ReasonCode.VERSION_SELECTED:
        return CompleteStage(
            status=StageStatus.COMPLETE,
            reason_code=ReasonCode.VERSION_SELECTED,
            diagnostics=(),
        )
    return CompleteStage(
        status=StageStatus.COMPLETE,
        reason_code=ReasonCode.COMPLETED,
        diagnostics=(),
    )


def _partial(reason: ReasonCode = ReasonCode.PARTIAL_COVERAGE) -> StageResult:
    if reason is ReasonCode.LEGACY_FALLBACK:
        return PartialStage(
            status=StageStatus.PARTIAL,
            reason_code=ReasonCode.LEGACY_FALLBACK,
            diagnostics=(),
        )
    if reason is ReasonCode.BUFFER_OVERFLOW:
        return PartialStage(
            status=StageStatus.PARTIAL,
            reason_code=ReasonCode.BUFFER_OVERFLOW,
            diagnostics=(),
        )
    return PartialStage(
        status=StageStatus.PARTIAL,
        reason_code=ReasonCode.PARTIAL_COVERAGE,
        diagnostics=(),
    )


def _incomplete(reason: ReasonCode = ReasonCode.DISCOVERY_FAILED) -> StageResult:
    if reason is ReasonCode.TIMEOUT:
        return IncompleteStage(
            status=StageStatus.INCOMPLETE,
            reason_code=ReasonCode.TIMEOUT,
            diagnostics=(),
        )
    return IncompleteStage(
        status=StageStatus.INCOMPLETE,
        reason_code=ReasonCode.DISCOVERY_FAILED,
        diagnostics=(),
    )


def _unsupported(reason: ReasonCode) -> StageResult:
    values = {
        ReasonCode.RUNTIME_UNAVAILABLE: UnsupportedStage(
            status=StageStatus.UNSUPPORTED,
            reason_code=ReasonCode.RUNTIME_UNAVAILABLE,
            diagnostics=(),
        ),
        ReasonCode.UNSUPPORTED_PLATFORM: UnsupportedStage(
            status=StageStatus.UNSUPPORTED,
            reason_code=ReasonCode.UNSUPPORTED_PLATFORM,
            diagnostics=(),
        ),
        ReasonCode.VERSION_UNSUPPORTED: UnsupportedStage(
            status=StageStatus.UNSUPPORTED,
            reason_code=ReasonCode.VERSION_UNSUPPORTED,
            diagnostics=(),
        ),
        ReasonCode.OFFLINE: UnsupportedStage(
            status=StageStatus.UNSUPPORTED,
            reason_code=ReasonCode.OFFLINE,
            diagnostics=(),
        ),
    }
    return values.get(reason, values[ReasonCode.RUNTIME_UNAVAILABLE])


def _not_requested(reason: ReasonCode = ReasonCode.NOT_APPLICABLE) -> StageResult:
    if reason is ReasonCode.MODERN_HANDSHAKE_NOT_REQUESTED:
        return NotRequestedStage(
            status=StageStatus.NOT_REQUESTED,
            reason_code=ReasonCode.MODERN_HANDSHAKE_NOT_REQUESTED,
            diagnostics=(),
        )
    return NotRequestedStage(
        status=StageStatus.NOT_REQUESTED,
        reason_code=ReasonCode.NOT_APPLICABLE,
        diagnostics=(),
    )


def _coverage(value: WatchCoverage | None, *, offline: bool) -> StageResult:
    if value is WatchCoverage.COMPLETE:
        return _complete()
    if value is WatchCoverage.UNSUPPORTED:
        return _unsupported(ReasonCode.OFFLINE if offline else ReasonCode.UNSUPPORTED_PLATFORM)
    return _partial()


def _probe(result: LocalWatchResult) -> StageResult:
    if result.status is LocalWatchStatus.COMPLETE:
        return _complete()
    if result.status is LocalWatchStatus.PARTIAL:
        return _partial()
    if result.status is LocalWatchStatus.UNSUPPORTED:
        return _unsupported(ReasonCode.VERSION_UNSUPPORTED)
    reason = ReasonCode.TIMEOUT if "TIMEOUT" in result.reason_code else ReasonCode.DISCOVERY_FAILED
    return _incomplete(reason)


def build_state(
    result: LocalWatchResult,
    completeness: DeclaredCompleteness,
    *,
    uncovered_events: int,
) -> ObservationState:
    if result.protocol is None:
        raise ValueError("PROTOCOL_EVIDENCE_MISSING")
    # The era is typed evidence from the completed negotiation; do not infer
    # modern discovery from a persisted string or from a missing handshake.
    modern = result.protocol.era is ProtocolEra.MODERN
    version = (
        _complete(ReasonCode.VERSION_SELECTED) if modern else _partial(ReasonCode.LEGACY_FALLBACK)
    )
    handshake = _not_requested(ReasonCode.MODERN_HANDSHAKE_NOT_REQUESTED) if modern else _complete()
    declared = _complete() if completeness is DeclaredCompleteness.COMPLETE else _partial()
    mapped = {
        name: _coverage(result.coverage.get(name), offline=result.offline)
        for name in ("file", "net", "process", "dns", "proxy", "snapshot", "stdio")
    }
    if uncovered_events:
        mapped["file"] = _partial()
        mapped["net"] = _partial()
        mapped["process"] = _partial()
    probe = _probe(result)
    idle = (
        _complete() if any(span.kind.value == "idle" for span in result.spans) else _not_requested()
    )
    stages = StageSet(
        install=_not_requested() if result.offline else _complete(),
        startup=_complete(),
        version_discovery=version,
        handshake=handshake,
        probe=probe,
        idle=idle,
        declared=declared,
        file=mapped["file"],
        net=mapped["net"],
    )
    coverage = Coverage(**mapped)
    entries = (
        stages.install,
        stages.startup,
        stages.version_discovery,
        stages.handshake,
        stages.probe,
        stages.idle,
        stages.declared,
        stages.file,
        stages.net,
        *tuple(mapped.values()),
    )
    complete = all(
        entry.status in {StageStatus.COMPLETE, StageStatus.NOT_REQUESTED} for entry in entries
    )
    overall = _complete() if complete else _partial()
    return ObservationState(overall=overall, stages=stages, coverage=coverage)


__all__ = ["build_state"]
