"""Typed engine boundaries and deterministic foundation request/result exports."""

from panopticon.engine.contracts import (
    CompleteResult,
    Coverage,
    EngineDiagnostic,
    EngineReason,
    EngineStatus,
    FailedResult,
    IncompleteResult,
    PartialResult,
    Result,
    UnsupportedResult,
)
from panopticon.engine.exit_codes import (
    NOT_IMPLEMENTED_EXIT,
    ExitInputs,
    resolve_exit_code,
    result_exit_code,
)

__all__ = [
    "NOT_IMPLEMENTED_EXIT",
    "CompleteResult",
    "Coverage",
    "EngineDiagnostic",
    "EngineReason",
    "EngineStatus",
    "ExitInputs",
    "FailedResult",
    "IncompleteResult",
    "PartialResult",
    "Result",
    "UnsupportedResult",
    "resolve_exit_code",
    "result_exit_code",
]
