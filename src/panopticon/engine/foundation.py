"""Deterministic foundation fixtures behind the thin CLI wrappers."""

from __future__ import annotations

from panopticon.engine.contracts import (
    CompleteResult,
    EngineDiagnostic,
    EngineReason,
    IncompleteResult,
    Result,
    UnsupportedResult,
)
from panopticon.engine.diff import DiffRequest
from panopticon.engine.doctor import DoctorRequest
from panopticon.engine.scan import ScanRequest
from panopticon.engine.watch import (
    TargetMode,
    TargetSelection,
    WatchOptions,
    WatchRequest,
)


def _not_implemented(epic: str) -> UnsupportedResult:
    return UnsupportedResult(
        reason_code=EngineReason.UNSUPPORTED_TRANSPORT,
        diagnostics=(EngineDiagnostic("NOT_IMPLEMENTED", epic),),
    )


def run_doctor(request: DoctorRequest) -> Result:
    if request.list_clients and request.client is None and not request.fix:
        return CompleteResult(reason_code=EngineReason.COMPLETED)
    if request.client is not None:
        return IncompleteResult(
            reason_code=EngineReason.DISCOVERY_FAILED,
            diagnostics=(EngineDiagnostic("DISCOVERY_FAILED", "DISCOVERY_FAILED"),),
        )
    return _not_implemented("E02")


def run_watch(request: WatchRequest) -> Result:
    return _not_implemented("E05")


def run_diff(request: DiffRequest) -> Result:
    return _not_implemented("E14")


def run_scan(request: ScanRequest) -> Result:
    return _not_implemented("E16")


__all__ = [
    "DiffRequest",
    "DoctorRequest",
    "ScanRequest",
    "TargetMode",
    "TargetSelection",
    "WatchOptions",
    "WatchRequest",
    "run_diff",
    "run_doctor",
    "run_scan",
    "run_watch",
]
