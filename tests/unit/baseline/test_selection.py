"""Contract tests for explicit and deterministic implicit baseline selection."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from panopticon.baseline.migrate import migrate_baseline_json
from panopticon.baseline.selection import baseline_kind, select_baseline
from panopticon.models.artifacts import Baseline, BaselineKind
from panopticon.models.observation import Observation


def observation(oid, at, installation="inst"):
    return Observation.model_construct(
        schema_version="0.1",
        observation_id=oid,
        installation_id=installation,
        observed_at=at,
        server_id="server",
        pano_version="0.1",
        sandbox=SimpleNamespace(),
        package_resolved=None,
        protocol=SimpleNamespace(),
        tools=(),
        spans=(),
        declared=SimpleNamespace(),
        findings=(),
        state=SimpleNamespace(),
    )


def baseline(kind=BaselineKind.EXPLICIT):
    return Baseline.model_construct(
        schema_version="0.1",
        baseline_id="baseline",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        label="release",
        kind=kind,
        inventory=(),
        observations=(),
        findings=(),
    )


def test_explicit_baseline_wins_without_mutating_observations():
    explicit = baseline()
    observations = [
        observation("old", datetime(2025, 1, 1, tzinfo=UTC)),
        observation("new", datetime(2025, 1, 2, tzinfo=UTC)),
    ]
    selected = select_baseline(explicit, observations)
    assert selected is explicit
    assert observations[0].observation_id == "old"
    assert baseline_kind(selected) is BaselineKind.EXPLICIT


def test_implicit_selection_uses_latest_timestamp_then_installation_tie_break():
    first = observation("first", datetime(2025, 1, 2, tzinfo=UTC), "a")
    second = observation("second", datetime(2025, 1, 2, tzinfo=UTC), "b")
    selected = select_baseline(None, [second, first])
    assert selected is second
    assert baseline_kind(selected) is BaselineKind.LAST_OBSERVATION


def test_empty_observations_have_no_implicit_baseline():
    assert select_baseline(None, ()) is None


def test_every_shipped_development_version_migrates_and_replays_idempotently():
    fixture = Path(__file__).resolve().parents[2] / "fixtures" / "schemas" / "baseline-0.0-dev.json"
    migrated = migrate_baseline_json(fixture.read_text())
    assert migrated.schema_version == "0.1"
    assert migrate_baseline_json(migrated.model_dump_json()) == migrated
