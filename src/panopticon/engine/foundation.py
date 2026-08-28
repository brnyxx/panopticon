"""Deterministic foundation fixtures behind the thin CLI wrappers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from panopticon.discovery.base import DiscoveryEnv
from panopticon.engine.contracts import (
    EngineDiagnostic,
    EngineReason,
    Result,
    UnsupportedResult,
)
from panopticon.engine.diff import DiffRequest
from panopticon.engine.diff import run_diff as _run_diff
from panopticon.engine.doctor import DoctorInputs, DoctorRequest
from panopticon.engine.doctor import run_doctor as _run_doctor
from panopticon.engine.doctor_model import DoctorOutcome
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
    return _run_doctor(request).result


def doctor_outcome(request: DoctorRequest) -> DoctorOutcome:
    """Run doctor with process runtime dependencies for the CLI boundary."""
    platform = "darwin" if sys.platform == "darwin" else "windows" if os.name == "nt" else "linux"
    env = DiscoveryEnv(Path.home(), Path.cwd(), platform, dict(os.environ))
    return _run_doctor(request, inputs=DoctorInputs(env))


def run_watch(request: WatchRequest) -> Result:
    return _not_implemented("E05")


def run_diff(request: DiffRequest) -> Result:
    return _run_diff(request).result


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
    "doctor_outcome",
    "run_diff",
    "run_doctor",
    "run_scan",
    "run_watch",
]
