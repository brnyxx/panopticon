"""Artifact normalization and canonical serialization before leak scanning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias, assert_never

from pydantic_core import PydanticSerializationError

from panopticon.models import Baseline, Finding, Observation, WrapRecord
from panopticon.store.contracts import (
    ArtifactInput,
    BinaryArtifact,
    ModelArtifact,
    RenderedArtifact,
    SinkKind,
)
from panopticon.util.canonicalize import (
    canonical_json_bytes,
    canonical_json_text_bytes,
    canonical_text_bytes,
)


@dataclass(frozen=True, slots=True)
class SerializedArtifact:
    data: bytes
    scan_texts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InvalidArtifact:
    """Serialization failure with optional logical text retained for leak scanning."""

    scan_texts: tuple[str, ...] = ()


SerializationResult: TypeAlias = SerializedArtifact | InvalidArtifact


def _model_artifact(artifact: ModelArtifact) -> SerializationResult:
    match artifact.kind:
        case SinkKind.OBSERVATION:
            model_matches = isinstance(artifact.model, Observation)
        case SinkKind.BASELINE:
            model_matches = isinstance(artifact.model, Baseline)
        case SinkKind.FINDING:
            model_matches = isinstance(artifact.model, Finding)
        case SinkKind.WRAP_RECORD:
            model_matches = isinstance(artifact.model, WrapRecord)
        case (
            SinkKind.CACHE
            | SinkKind.ALERT
            | SinkKind.JOURNAL
            | SinkKind.BACKUP
            | SinkKind.LOG
            | SinkKind.JSON
        ):
            model_matches = True
        case SinkKind.SARIF | SinkKind.MARKDOWN | SinkKind.PNG | SinkKind.SVG:
            return InvalidArtifact()
        case unreachable:
            assert_never(unreachable)
    if not model_matches:
        return InvalidArtifact()
    data = canonical_json_bytes(artifact.model)
    return SerializedArtifact(data, (data.decode("utf-8"),))


def _rendered_artifact(artifact: RenderedArtifact) -> SerializationResult:
    model_text = canonical_json_bytes(artifact.render_model).decode("utf-8")
    match artifact.kind:
        case SinkKind.SARIF:
            try:
                data = canonical_json_text_bytes(artifact.text)
            except (UnicodeError, ValueError):
                return InvalidArtifact((model_text, artifact.text))
        case SinkKind.MARKDOWN | SinkKind.SVG:
            try:
                data = canonical_text_bytes(artifact.text)
            except UnicodeError:
                return InvalidArtifact((model_text, artifact.text))
        case (
            SinkKind.CACHE
            | SinkKind.OBSERVATION
            | SinkKind.BASELINE
            | SinkKind.FINDING
            | SinkKind.WRAP_RECORD
            | SinkKind.ALERT
            | SinkKind.JOURNAL
            | SinkKind.BACKUP
            | SinkKind.LOG
            | SinkKind.JSON
            | SinkKind.PNG
        ):
            return InvalidArtifact()
        case unreachable:
            assert_never(unreachable)
    return SerializedArtifact(data, (model_text, data.decode("utf-8")))


def _binary_artifact(artifact: BinaryArtifact) -> SerializationResult:
    match artifact.kind:
        case SinkKind.PNG:
            model_text = canonical_json_bytes(artifact.render_model).decode("utf-8")
            return SerializedArtifact(
                artifact.data,
                (model_text, artifact.data.decode("utf-8", errors="ignore")),
            )
        case (
            SinkKind.CACHE
            | SinkKind.OBSERVATION
            | SinkKind.BASELINE
            | SinkKind.FINDING
            | SinkKind.WRAP_RECORD
            | SinkKind.ALERT
            | SinkKind.JOURNAL
            | SinkKind.BACKUP
            | SinkKind.LOG
            | SinkKind.JSON
            | SinkKind.SARIF
            | SinkKind.MARKDOWN
            | SinkKind.SVG
        ):
            return InvalidArtifact()
        case unreachable:
            assert_never(unreachable)


def serialize_artifact(artifact: ArtifactInput) -> SerializationResult:
    """Normalize one closed artifact variant to bytes plus pre-encoding scan inputs."""
    try:
        match artifact:
            case ModelArtifact():
                return _model_artifact(artifact)
            case RenderedArtifact():
                return _rendered_artifact(artifact)
            case BinaryArtifact():
                return _binary_artifact(artifact)
            case unreachable:
                assert_never(unreachable)
    except (PydanticSerializationError, UnicodeError, ValueError):
        return InvalidArtifact()
