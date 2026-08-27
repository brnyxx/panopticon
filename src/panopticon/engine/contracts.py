"""Immutable typed outcomes shared by the foundation engine boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum, unique
from typing import Literal, TypeAlias

from panopticon.models import Coverage, NotRequestedStage, ReasonCode, StageStatus


@unique
class EngineStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"


@unique
class EngineReason(StrEnum):
    COMPLETED = "COMPLETED"
    VERSION_SELECTED = "VERSION_SELECTED"
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
    LEGACY_FALLBACK = "LEGACY_FALLBACK"
    BUFFER_OVERFLOW = "BUFFER_OVERFLOW"
    TIMEOUT = "TIMEOUT"
    DISCOVERY_FAILED = "DISCOVERY_FAILED"
    STAGE_ERROR = "STAGE_ERROR"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    RUNTIME_UNAVAILABLE = "RUNTIME_UNAVAILABLE"
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
    UNSUPPORTED_TRANSPORT = "UNSUPPORTED_TRANSPORT"
    VERSION_UNSUPPORTED = "VERSION_UNSUPPORTED"
    OFFLINE = "OFFLINE"


@dataclass(frozen=True, slots=True)
class EngineDiagnostic:
    """A value-only diagnostic that never carries an exception object."""

    code: str
    detail: str

    def __post_init__(self) -> None:
        if not self.code or not self.code.isupper():
            raise ValueError("diagnostic code must be uppercase")
        if not self.detail:
            raise ValueError("diagnostic detail must be non-empty")


_NOT_REQUESTED_STAGE = NotRequestedStage(
    status=StageStatus.NOT_REQUESTED,
    reason_code=ReasonCode.NOT_APPLICABLE,
    diagnostics=(),
)


def _not_requested_coverage() -> Coverage:
    return Coverage(
        file=_NOT_REQUESTED_STAGE,
        net=_NOT_REQUESTED_STAGE,
        process=_NOT_REQUESTED_STAGE,
        dns=_NOT_REQUESTED_STAGE,
        proxy=_NOT_REQUESTED_STAGE,
        snapshot=_NOT_REQUESTED_STAGE,
        stdio=_NOT_REQUESTED_STAGE,
    )


_COMPLETE_REASONS = frozenset({EngineReason.COMPLETED, EngineReason.VERSION_SELECTED})
_PARTIAL_REASONS = frozenset(
    {EngineReason.PARTIAL_COVERAGE, EngineReason.LEGACY_FALLBACK, EngineReason.BUFFER_OVERFLOW}
)
_INCOMPLETE_REASONS = frozenset({EngineReason.TIMEOUT, EngineReason.DISCOVERY_FAILED})
_FAILED_REASONS = frozenset(
    {EngineReason.STAGE_ERROR, EngineReason.PROTOCOL_ERROR, EngineReason.TRANSPORT_ERROR}
)
_UNSUPPORTED_REASONS = frozenset(
    {
        EngineReason.RUNTIME_UNAVAILABLE,
        EngineReason.UNSUPPORTED_PLATFORM,
        EngineReason.UNSUPPORTED_TRANSPORT,
        EngineReason.VERSION_UNSUPPORTED,
        EngineReason.OFFLINE,
    }
)


def _validate_result(
    status: EngineStatus,
    expected_status: EngineStatus,
    reason_code: EngineReason,
    allowed_reasons: frozenset[EngineReason],
    coverage: Coverage,
    diagnostics: tuple[EngineDiagnostic, ...],
) -> None:
    if (
        not isinstance(status, EngineStatus)
        or status is not expected_status
        or not isinstance(reason_code, EngineReason)
        or reason_code not in allowed_reasons
        or not isinstance(coverage, Coverage)
        or not isinstance(diagnostics, tuple)
        or not all(isinstance(diagnostic, EngineDiagnostic) for diagnostic in diagnostics)
    ):
        raise ValueError("result fields are not an allowed immutable typed boundary")


@dataclass(frozen=True, slots=True)
class CompleteResult:
    status: Literal[EngineStatus.COMPLETE] = EngineStatus.COMPLETE
    reason_code: Literal[EngineReason.COMPLETED, EngineReason.VERSION_SELECTED] = (
        EngineReason.COMPLETED
    )
    coverage: Coverage = field(default_factory=_not_requested_coverage)
    diagnostics: tuple[EngineDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        _validate_result(
            self.status,
            EngineStatus.COMPLETE,
            self.reason_code,
            _COMPLETE_REASONS,
            self.coverage,
            self.diagnostics,
        )


@dataclass(frozen=True, slots=True)
class PartialResult:
    status: Literal[EngineStatus.PARTIAL] = EngineStatus.PARTIAL
    reason_code: Literal[
        EngineReason.PARTIAL_COVERAGE,
        EngineReason.LEGACY_FALLBACK,
        EngineReason.BUFFER_OVERFLOW,
    ] = EngineReason.PARTIAL_COVERAGE
    coverage: Coverage = field(default_factory=_not_requested_coverage)
    diagnostics: tuple[EngineDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        _validate_result(
            self.status,
            EngineStatus.PARTIAL,
            self.reason_code,
            _PARTIAL_REASONS,
            self.coverage,
            self.diagnostics,
        )


@dataclass(frozen=True, slots=True)
class IncompleteResult:
    status: Literal[EngineStatus.INCOMPLETE] = EngineStatus.INCOMPLETE
    reason_code: Literal[EngineReason.TIMEOUT, EngineReason.DISCOVERY_FAILED] = EngineReason.TIMEOUT
    coverage: Coverage = field(default_factory=_not_requested_coverage)
    diagnostics: tuple[EngineDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        _validate_result(
            self.status,
            EngineStatus.INCOMPLETE,
            self.reason_code,
            _INCOMPLETE_REASONS,
            self.coverage,
            self.diagnostics,
        )


@dataclass(frozen=True, slots=True)
class FailedResult:
    status: Literal[EngineStatus.FAILED] = EngineStatus.FAILED
    reason_code: Literal[
        EngineReason.STAGE_ERROR,
        EngineReason.PROTOCOL_ERROR,
        EngineReason.TRANSPORT_ERROR,
    ] = EngineReason.STAGE_ERROR
    coverage: Coverage = field(default_factory=_not_requested_coverage)
    diagnostics: tuple[EngineDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        _validate_result(
            self.status,
            EngineStatus.FAILED,
            self.reason_code,
            _FAILED_REASONS,
            self.coverage,
            self.diagnostics,
        )


@dataclass(frozen=True, slots=True)
class UnsupportedResult:
    status: Literal[EngineStatus.UNSUPPORTED] = EngineStatus.UNSUPPORTED
    reason_code: Literal[
        EngineReason.RUNTIME_UNAVAILABLE,
        EngineReason.UNSUPPORTED_PLATFORM,
        EngineReason.UNSUPPORTED_TRANSPORT,
        EngineReason.VERSION_UNSUPPORTED,
        EngineReason.OFFLINE,
    ] = EngineReason.UNSUPPORTED_TRANSPORT
    coverage: Coverage = field(default_factory=_not_requested_coverage)
    diagnostics: tuple[EngineDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        _validate_result(
            self.status,
            EngineStatus.UNSUPPORTED,
            self.reason_code,
            _UNSUPPORTED_REASONS,
            self.coverage,
            self.diagnostics,
        )


Result: TypeAlias = (
    CompleteResult | PartialResult | IncompleteResult | FailedResult | UnsupportedResult
)


__all__ = [
    "CompleteResult",
    "Coverage",
    "EngineDiagnostic",
    "EngineReason",
    "EngineStatus",
    "FailedResult",
    "IncompleteResult",
    "PartialResult",
    "Result",
    "UnsupportedResult",
]
