"""Self-contained persisted finding records used by observations and baselines."""

from __future__ import annotations

from enum import StrEnum, unique
from typing import Annotated

from pydantic import Field

from panopticon.models.common import (
    NonEmptyStr,
    PersistedPathValue,
    SchemaVersion,
    StrictModel,
    UtcDateTime,
)
from panopticon.models.ids import (
    FindingIdValue,
    InstallationIdValue,
    LogicalKeyValue,
    ObservationIdValue,
    ServerIdValue,
    SpanIdValue,
)


@unique
class FindingSeverity(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


@unique
class FindingKind(StrEnum):
    CONFIRMED = "confirmed"
    REVIEW = "review"
    INFO = "info"


@unique
class EvidenceKind(StrEnum):
    PATH = "PATH"
    HOST = "HOST"
    PROCESS = "PROCESS"
    DECOY = "DECOY"
    CONFIG = "CONFIG"
    PROTOCOL = "PROTOCOL"


class FindingEvidence(StrictModel):
    kind: EvidenceKind
    subject: NonEmptyStr
    value: NonEmptyStr


class SourceLocation(StrictModel):
    path: PersistedPathValue
    line: Annotated[int, Field(ge=1)]
    column: Annotated[int, Field(ge=1)]


class Finding(StrictModel):
    schema_version: SchemaVersion
    id: FindingIdValue
    logical_key: LogicalKeyValue
    rule_id: Annotated[str, Field(pattern=r"^(CFG|HIST|WATCH|FIX|SENT)-\d{3}$")]
    severity: FindingSeverity | None
    kind: FindingKind
    title: NonEmptyStr
    evidence: tuple[FindingEvidence, ...]
    location: SourceLocation | None
    server_id: ServerIdValue
    installation_id: InstallationIdValue
    observation_id: ObservationIdValue
    span_ref: SpanIdValue | None
    remediation_key: NonEmptyStr | None
    fix_available: bool
    declared_source: NonEmptyStr | None
    first_seen: UtcDateTime
    suppressed_by: NonEmptyStr | None
