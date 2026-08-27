"""Closed typed contracts for every product persistence sink."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import Protocol, TypeAlias

from panopticon.models.common import NonEmptyStr, SchemaVersion, StrictModel
from panopticon.util.leak_check import LeakHit


@unique
class SinkKind(StrEnum):
    CACHE = "cache"
    OBSERVATION = "observation"
    BASELINE = "baseline"
    FINDING = "finding"
    WRAP_RECORD = "wrap_record"
    ALERT = "alert"
    JOURNAL = "journal"
    BACKUP = "backup"
    LOG = "log"
    JSON = "json"
    SARIF = "sarif"
    MARKDOWN = "markdown"
    PNG = "png"
    SVG = "svg"


@unique
class AtomicOperation(StrEnum):
    OPEN_PARENT = "OPEN_PARENT"
    CREATE_TEMP = "CREATE_TEMP"
    WRITE = "WRITE"
    FLUSH = "FLUSH"
    FILE_FSYNC = "FILE_FSYNC"
    REPLACE = "REPLACE"
    DIRECTORY_FSYNC = "DIRECTORY_FSYNC"
    CLEANUP = "CLEANUP"


@unique
class DirectorySyncStatus(StrEnum):
    SYNCED = "SYNCED"
    UNSUPPORTED = "UNSUPPORTED"


@unique
class RejectionCode(StrEnum):
    LEAK_DETECTED = "LEAK_DETECTED"
    INVALID_ARTIFACT = "INVALID_ARTIFACT"
    UNSAFE_PARENT = "UNSAFE_PARENT"
    SYMLINK_TARGET = "SYMLINK_TARGET"
    UNSAFE_TARGET = "UNSAFE_TARGET"


@unique
class FailureCode(StrEnum):
    FILESYSTEM_ERROR = "FILESYSTEM_ERROR"
    CLEANUP_ERROR = "CLEANUP_ERROR"


class FaultInjector(Protocol):
    """Deterministic operation boundary used by filesystem failure tests."""

    def before(self, operation: AtomicOperation) -> None: ...


class RenderField(StrictModel):
    name: NonEmptyStr
    value: str


class RenderModel(StrictModel):
    """Sanitized machine-readable source for text and binary reporters."""

    schema_version: SchemaVersion
    title: NonEmptyStr
    fields: tuple[RenderField, ...]


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    kind: SinkKind
    model: StrictModel


@dataclass(frozen=True, slots=True)
class RenderedArtifact:
    kind: SinkKind
    render_model: RenderModel
    text: str


@dataclass(frozen=True, slots=True)
class BinaryArtifact:
    kind: SinkKind
    render_model: RenderModel
    data: bytes


ArtifactInput: TypeAlias = ModelArtifact | RenderedArtifact | BinaryArtifact


@dataclass(frozen=True, slots=True)
class PersistRequest:
    target: Path
    artifact: ArtifactInput


@dataclass(frozen=True, slots=True)
class PersistSuccess:
    target: Path
    kind: SinkKind
    bytes_written: int
    directory_sync: DirectorySyncStatus


@dataclass(frozen=True, slots=True)
class PersistRejected:
    target: Path
    kind: SinkKind
    code: RejectionCode
    leak_hits: tuple[LeakHit, ...] = ()


@dataclass(frozen=True, slots=True)
class PersistFailure:
    target: Path
    kind: SinkKind
    code: FailureCode
    operation: AtomicOperation
    target_replaced: bool


PersistResult: TypeAlias = PersistSuccess | PersistRejected | PersistFailure
