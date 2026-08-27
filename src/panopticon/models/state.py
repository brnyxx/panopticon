"""Exhaustive stage outcomes, reasons, diagnostics, and coverage."""

from __future__ import annotations

from enum import StrEnum, unique
from typing import Annotated, Literal, Self, TypeAlias

from pydantic import Field, model_validator

from panopticon.models.common import ContractViolationError, NonEmptyStr, StrictModel


@unique
class StageStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"
    SKIPPED = "SKIPPED"
    NOT_REQUESTED = "NOT_REQUESTED"


@unique
class ReasonCode(StrEnum):
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
    SKIPPED_DESTRUCTIVE = "SKIPPED_DESTRUCTIVE"
    USER_SKIPPED = "USER_SKIPPED"
    MODERN_HANDSHAKE_NOT_REQUESTED = "MODERN_HANDSHAKE_NOT_REQUESTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Diagnostic(StrictModel):
    code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]+$")]
    detail: NonEmptyStr


class CompleteStage(StrictModel):
    status: Literal[StageStatus.COMPLETE]
    reason_code: Literal[ReasonCode.COMPLETED, ReasonCode.VERSION_SELECTED]
    diagnostics: tuple[Diagnostic, ...]


class PartialStage(StrictModel):
    status: Literal[StageStatus.PARTIAL]
    reason_code: Literal[
        ReasonCode.PARTIAL_COVERAGE, ReasonCode.LEGACY_FALLBACK, ReasonCode.BUFFER_OVERFLOW
    ]
    diagnostics: tuple[Diagnostic, ...]


class IncompleteStage(StrictModel):
    status: Literal[StageStatus.INCOMPLETE]
    reason_code: Literal[ReasonCode.TIMEOUT, ReasonCode.DISCOVERY_FAILED]
    diagnostics: tuple[Diagnostic, ...]


class FailedStage(StrictModel):
    status: Literal[StageStatus.FAILED]
    reason_code: Literal[
        ReasonCode.STAGE_ERROR, ReasonCode.PROTOCOL_ERROR, ReasonCode.TRANSPORT_ERROR
    ]
    diagnostics: tuple[Diagnostic, ...]


class UnsupportedStage(StrictModel):
    status: Literal[StageStatus.UNSUPPORTED]
    reason_code: Literal[
        ReasonCode.RUNTIME_UNAVAILABLE,
        ReasonCode.UNSUPPORTED_PLATFORM,
        ReasonCode.UNSUPPORTED_TRANSPORT,
        ReasonCode.VERSION_UNSUPPORTED,
        ReasonCode.OFFLINE,
    ]
    diagnostics: tuple[Diagnostic, ...]


class SkippedStage(StrictModel):
    status: Literal[StageStatus.SKIPPED]
    reason_code: Literal[ReasonCode.SKIPPED_DESTRUCTIVE, ReasonCode.USER_SKIPPED]
    diagnostics: tuple[Diagnostic, ...]


class NotRequestedStage(StrictModel):
    status: Literal[StageStatus.NOT_REQUESTED]
    reason_code: Literal[ReasonCode.MODERN_HANDSHAKE_NOT_REQUESTED, ReasonCode.NOT_APPLICABLE]
    diagnostics: tuple[Diagnostic, ...]


StageResult: TypeAlias = Annotated[
    CompleteStage
    | PartialStage
    | IncompleteStage
    | FailedStage
    | UnsupportedStage
    | SkippedStage
    | NotRequestedStage,
    Field(discriminator="status"),
]


class StageSet(StrictModel):
    install: StageResult
    startup: StageResult
    version_discovery: StageResult
    handshake: StageResult
    probe: StageResult
    idle: StageResult
    declared: StageResult
    file: StageResult
    net: StageResult


class Coverage(StrictModel):
    file: StageResult
    net: StageResult
    process: StageResult
    dns: StageResult
    proxy: StageResult
    snapshot: StageResult
    stdio: StageResult


class ObservationState(StrictModel):
    overall: StageResult
    stages: StageSet
    coverage: Coverage

    @model_validator(mode="after")
    def enforce_overall_coverage(self) -> Self:
        entries = (
            self.stages.install,
            self.stages.startup,
            self.stages.version_discovery,
            self.stages.handshake,
            self.stages.probe,
            self.stages.idle,
            self.stages.declared,
            self.stages.file,
            self.stages.net,
            self.coverage.file,
            self.coverage.net,
            self.coverage.process,
            self.coverage.dns,
            self.coverage.proxy,
            self.coverage.snapshot,
            self.coverage.stdio,
        )
        complete_states = {StageStatus.COMPLETE, StageStatus.NOT_REQUESTED}
        if self.overall.status is StageStatus.COMPLETE and any(
            entry.status not in complete_states for entry in entries
        ):
            raise ContractViolationError(
                "INVALID_OVERALL_STATUS", "COMPLETE masks incomplete coverage"
            )
        if self.overall.status is StageStatus.PARTIAL and all(
            entry.status in complete_states for entry in entries
        ):
            raise ContractViolationError("INVALID_OVERALL_STATUS", "PARTIAL has no degraded stage")
        return self
