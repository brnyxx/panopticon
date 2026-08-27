"""Explicit idempotent development-line baseline migrations."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias, assert_never

from pydantic import Field, TypeAdapter

from panopticon.models.artifacts import Baseline, BaselineKind
from panopticon.models.common import StrictModel, UtcDateTime
from panopticon.models.finding import Finding
from panopticon.models.ids import BaselineIdValue
from panopticon.models.inventory import InstalledServer
from panopticon.models.observation import Observation


class DevelopmentBaselineV0(StrictModel):
    """Explicit never-published fixture shape preceding schema 0.1."""

    schema_version: Literal["0.0"]
    baseline_id: BaselineIdValue
    created_at: UtcDateTime
    kind: BaselineKind
    inventory: tuple[InstalledServer, ...]
    observations: tuple[Observation, ...]
    findings: tuple[Finding, ...]


MigrationInput: TypeAlias = Annotated[
    DevelopmentBaselineV0 | Baseline, Field(discriminator="schema_version")
]
_MIGRATION_ADAPTER: TypeAdapter[MigrationInput] = TypeAdapter(MigrationInput)


def migrate_baseline_json(payload: str) -> Baseline:
    """Dispatch by source version and converge idempotently on schema 0.1."""
    record = _MIGRATION_ADAPTER.validate_json(payload)
    match record:
        case DevelopmentBaselineV0():
            return Baseline(
                schema_version="0.1",
                baseline_id=record.baseline_id,
                created_at=record.created_at,
                label=None,
                kind=record.kind,
                inventory=record.inventory,
                observations=record.observations,
                findings=record.findings,
            )
        case Baseline():
            return record
        case unreachable:
            assert_never(unreachable)
