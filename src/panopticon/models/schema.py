"""Deterministic JSON Schema generation and runtime dispatch."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Final, TypeAlias, assert_never

from pydantic import BaseModel

from panopticon.models.artifacts import Baseline, DiffResult, WrapRecord
from panopticon.models.event import Event
from panopticon.models.finding import Finding
from panopticon.models.inventory import InstalledServer
from panopticon.models.observation import Observation


@unique
class SchemaName(StrEnum):
    INSTALLED_SERVER = "installed_server"
    EVENT = "event"
    FINDING = "finding"
    OBSERVATION = "observation"
    BASELINE = "baseline"
    DIFF_RESULT = "diff_result"
    WRAP_RECORD = "wrap_record"


PersistedRecord: TypeAlias = (
    InstalledServer | Event | Finding | Observation | Baseline | DiffResult | WrapRecord
)


@dataclass(frozen=True, slots=True)
class SchemaDocument:
    name: str
    content: str


_SCHEMA_MODELS: Final[tuple[tuple[SchemaName, type[BaseModel]], ...]] = (
    (SchemaName.INSTALLED_SERVER, InstalledServer),
    (SchemaName.EVENT, Event),
    (SchemaName.FINDING, Finding),
    (SchemaName.OBSERVATION, Observation),
    (SchemaName.BASELINE, Baseline),
    (SchemaName.DIFF_RESULT, DiffResult),
    (SchemaName.WRAP_RECORD, WrapRecord),
)


def generate_schema_documents() -> tuple[SchemaDocument, ...]:
    """Generate canonical self-contained 2020-12 schemas from runtime models."""
    documents: list[SchemaDocument] = []
    for name, model in _SCHEMA_MODELS:
        schema = model.model_json_schema(mode="serialization", ref_template="#/$defs/{model}")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"https://panopticon.dev/schemas/{name.value}.json"
        content = f"{json.dumps(schema, indent=2, sort_keys=True)}\n"
        documents.append(SchemaDocument(name=f"{name.value}.json", content=content))
    return tuple(documents)


def validate_runtime_json(name: SchemaName, payload: str) -> PersistedRecord:
    """Parse one persisted JSON record through its authoritative runtime model."""
    match name:
        case SchemaName.INSTALLED_SERVER:
            return InstalledServer.model_validate_json(payload)
        case SchemaName.EVENT:
            return Event.model_validate_json(payload)
        case SchemaName.FINDING:
            return Finding.model_validate_json(payload)
        case SchemaName.OBSERVATION:
            return Observation.model_validate_json(payload)
        case SchemaName.BASELINE:
            return Baseline.model_validate_json(payload)
        case SchemaName.DIFF_RESULT:
            return DiffResult.model_validate_json(payload)
        case SchemaName.WRAP_RECORD:
            return WrapRecord.model_validate_json(payload)
        case unreachable:
            assert_never(unreachable)
