"""Baseline and observation repository lifecycle tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from panopticon.baseline.service import build_baseline
from panopticon.models.artifacts import Baseline, BaselineKind
from panopticon.models.observation import Observation
from panopticon.store.contracts import PersistRejected, PersistSuccess, RejectionCode
from panopticon.store.repository import ArtifactRepository, LoadStatus, RemoveStatus
from panopticon.util.leak_check import LeakContext


def _baseline(label: str = "checkpoint") -> Baseline:
    return Baseline(
        schema_version="1.0",
        baseline_id="bl_0000000000000001",
        created_at=datetime(2026, 8, 28, tzinfo=UTC),
        label=label,
        kind=BaselineKind.EXPLICIT,
        inventory=(),
        observations=(),
        findings=(),
    )


def test_baseline_repository_round_trip_and_remove(tmp_path) -> None:
    repository = ArtifactRepository(tmp_path, LeakContext(home_paths=("/real/home",)))
    result = repository.persist_baseline(_baseline())
    assert isinstance(result, PersistSuccess)
    loaded = repository.load_baseline("bl_0000000000000001")
    assert loaded.status is LoadStatus.AVAILABLE
    assert loaded.baseline == _baseline()
    assert repository.list_baselines() == (loaded,)
    assert repository.remove_baseline("bl_0000000000000001") is RemoveStatus.REMOVED
    assert repository.remove_baseline("bl_0000000000000001") is RemoveStatus.NOT_FOUND


def test_baseline_repository_rejects_leak_and_symlink(tmp_path) -> None:
    repository = ArtifactRepository(tmp_path, LeakContext(secrets=("private-value",)))
    rejected = repository.persist_baseline(_baseline("private-value"))
    assert isinstance(rejected, PersistRejected)
    assert rejected.code is RejectionCode.LEAK_DETECTED
    directory = tmp_path / "baselines"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "bl_0000000000000002.json"
    target.symlink_to(directory / "missing.json")
    assert repository.load_baseline(target.stem).reason_code == "SYMLINK_REJECTED"


def test_build_baseline_selects_latest_observation_deterministically() -> None:
    earlier = Observation.model_validate_json(
        Path("tests/fixtures/schemas/observation.json").read_text(encoding="utf-8")
    )
    later = earlier.model_copy(
        update={
            "observation_id": "obs_later",
            "observed_at": earlier.observed_at + timedelta(days=1),
        }
    )
    baseline = build_baseline(
        (),
        (later, earlier),
        now=datetime(2026, 8, 28, tzinfo=UTC),
        label="deterministic",
    )
    repeated = build_baseline(
        (),
        (earlier, later),
        now=datetime(2026, 8, 29, tzinfo=UTC),
        label="deterministic",
    )
    assert baseline.observations == (later,)
    assert baseline.baseline_id == repeated.baseline_id
