"""Baseline migrations dispatch through the one-time 1.0 freeze."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from panopticon.baseline.migrate import migrate_baseline_json

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "schemas"


def test_development_baseline_migration_replay_is_idempotent() -> None:
    # Given: an explicit pre-0.1 development fixture.
    payload = (FIXTURES / "baseline-0.0-dev.json").read_text()

    # When: it is migrated and the migrated artifact is replayed.
    migrated = migrate_baseline_json(payload)
    replayed = migrate_baseline_json(migrated.model_dump_json())

    # Then: dispatch converges exactly on the current immutable model.
    assert migrated.schema_version == "1.0"
    assert replayed == migrated
    assert migrated.label is None


def test_schema_0_1_baseline_converges_to_frozen_schema() -> None:
    payload = (FIXTURES / "baseline.json").read_text().replace('"1.0"', '"0.1"')

    migrated = migrate_baseline_json(payload)
    replayed = migrate_baseline_json(migrated.model_dump_json())

    assert migrated.schema_version == "1.0"
    assert replayed == migrated


def test_unknown_or_malformed_1_0_versions_are_rejected() -> None:
    # Given: an unknown development version and an incomplete frozen artifact.
    unknown = '{"schema_version":"0.8"}'
    malformed = '{"schema_version":"1.0"}'

    # When / Then: neither is silently treated as publicly shipped input.
    with pytest.raises(ValidationError):
        migrate_baseline_json(unknown)
    with pytest.raises(ValidationError):
        migrate_baseline_json(malformed)
