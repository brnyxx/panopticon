"""Development-line baseline migrations dispatch explicitly and replay idempotently."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from panopticon.baseline.migrate import migrate_baseline_json

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "schemas"


def test_development_baseline_migration_replay_is_idempotent() -> None:
    # Given: an explicit pre-0.1 development fixture, not the scaffold's false 1.0 claim.
    payload = (FIXTURES / "baseline-0.0-dev.json").read_text()

    # When: it is migrated and the migrated artifact is replayed.
    migrated = migrate_baseline_json(payload)
    replayed = migrate_baseline_json(migrated.model_dump_json())

    # Then: dispatch converges exactly on the current immutable model.
    assert migrated.schema_version == "0.1"
    assert replayed == migrated
    assert migrated.label is None


def test_unknown_or_scaffold_1_0_versions_are_rejected() -> None:
    # Given: versions with no explicit development-line migration.
    unknown = '{"schema_version":"0.8"}'
    scaffold = '{"schema_version":"1.0"}'

    # When / Then: neither is silently treated as publicly shipped input.
    with pytest.raises(ValidationError):
        migrate_baseline_json(unknown)
    with pytest.raises(ValidationError):
        migrate_baseline_json(scaffold)
