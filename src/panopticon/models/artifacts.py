"""Baseline, diff, and wrap persisted records."""

from __future__ import annotations

from enum import StrEnum, unique

from panopticon.models.common import NonEmptyStr, SchemaVersion, StrictModel, UtcDateTime
from panopticon.models.event import Event
from panopticon.models.finding import Finding
from panopticon.models.ids import (
    BaselineIdValue,
    InstallationIdValue,
    ServerIdValue,
    SpanIdValue,
)
from panopticon.models.inventory import InstalledServer
from panopticon.models.observation import Observation
from panopticon.models.state import Coverage


@unique
class BaselineKind(StrEnum):
    EXPLICIT = "explicit"
    LAST_OBSERVATION = "last_observation"
    IMPLICIT_MTIME = "implicit_mtime"


class Baseline(StrictModel):
    schema_version: SchemaVersion
    baseline_id: BaselineIdValue
    created_at: UtcDateTime
    label: NonEmptyStr | None
    kind: BaselineKind
    inventory: tuple[InstalledServer, ...]
    observations: tuple[Observation, ...]
    findings: tuple[Finding, ...]


class DiffEntry(StrictModel):
    kind: NonEmptyStr
    installation_id: InstallationIdValue
    key: NonEmptyStr
    detail: NonEmptyStr


class FindingChanges(StrictModel):
    new: tuple[DiffEntry, ...]
    changed: tuple[DiffEntry, ...]
    unchanged: tuple[DiffEntry, ...]
    resolved: tuple[DiffEntry, ...]
    unknown: tuple[DiffEntry, ...]


class DiffResult(StrictModel):
    schema_version: SchemaVersion
    since: NonEmptyStr
    until: NonEmptyStr
    findings: FindingChanges
    capability: tuple[DiffEntry, ...]
    behavior: tuple[DiffEntry, ...]
    inventory: tuple[DiffEntry, ...]
    meaningful: tuple[DiffEntry, ...]


class WrapSpan(StrictModel):
    span_id: SpanIdValue
    tool: NonEmptyStr
    request_id: NonEmptyStr
    duration_ms: int


class WrapRecord(StrictModel):
    schema_version: SchemaVersion
    ts: UtcDateTime
    server_id: ServerIdValue
    installation_id: InstallationIdValue
    span: WrapSpan
    events: tuple[Event, ...]
    coverage: Coverage
