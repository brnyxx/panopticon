from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

import panopticon.store.repository as repository_module
from panopticon.models import Baseline, Observation, WrapRecord
from panopticon.store.contracts import PersistSuccess
from panopticon.store.repository import ArtifactRepository, LoadStatus, RemoveStatus
from panopticon.store.unlink import ReadStatus, UnlinkStatus

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "schemas"


def _baseline() -> Baseline:
    return Baseline.model_validate_json((FIXTURES / "baseline.json").read_text())


def _observation() -> Observation:
    return Observation.model_validate_json((FIXTURES / "observation.json").read_text())


def _wrap() -> WrapRecord:
    return WrapRecord.model_validate_json((FIXTURES / "wrap_record.json").read_text())


def test_baseline_load_statuses_and_migration(tmp_path: Path) -> None:
    repo = ArtifactRepository(tmp_path)
    baseline = _baseline()
    assert repo.load_baseline(baseline.baseline_id).status is LoadStatus.NOT_FOUND
    assert isinstance(repo.persist_baseline(baseline), PersistSuccess)
    loaded = repo.load_baseline(baseline.baseline_id)
    assert loaded.status is LoadStatus.AVAILABLE
    assert loaded.baseline == baseline
    path = tmp_path / "baselines" / f"{baseline.baseline_id}.json"
    path.write_text("{not-json")
    invalid = repo.load_baseline(baseline.baseline_id)
    assert invalid.status is LoadStatus.INVALID
    assert invalid.reason_code == "BASELINE_INVALID"


def test_load_rejects_symlink_and_permission_and_read_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = ArtifactRepository(tmp_path)
    target = tmp_path / "baselines" / "bl_deadbeef.json"
    target.parent.mkdir()
    target.write_text("{}")
    link = target.with_name("bl_link.json")
    link.symlink_to(target)
    assert repo.load_baseline("bl_link").reason_code == "SYMLINK_REJECTED"
    monkeypatch.setattr(
        repository_module,
        "read_regular",
        lambda _path: (ReadStatus.PERMISSION, None),
    )
    assert repo.load_baseline("bl_deadbeef").status is LoadStatus.PERMISSION

    monkeypatch.setattr(
        repository_module,
        "read_regular",
        lambda _path: (ReadStatus.FAILED, None),
    )
    assert repo.load_baseline("bl_deadbeef").reason_code == "BASELINE_READ_FAILED"


def test_list_and_remove_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = ArtifactRepository(tmp_path)
    baseline = _baseline()
    assert isinstance(repo.persist_baseline(baseline), PersistSuccess)
    assert repo.list_baselines()[0].baseline == baseline
    assert repo.remove_baseline("bl_missing") is RemoveStatus.NOT_FOUND
    assert repo.remove_baseline(baseline.baseline_id) is RemoveStatus.REMOVED
    target = tmp_path / "baselines" / "bl_link.json"
    target.parent.mkdir(exist_ok=True)
    real = target.with_name("real.json")
    real.write_text("{}")
    target.symlink_to(real)
    assert repo.remove_baseline("bl_link") is RemoveStatus.REJECTED
    monkeypatch.setattr(
        repository_module,
        "unlink_regular",
        lambda _path: UnlinkStatus.FAILED,
    )
    assert repo.remove_baseline("bl_fail") is RemoveStatus.FAILED


def test_baseline_paths_reject_traversal_and_symlinked_parent(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "bl_target.json"
    target.write_text("{}")
    root = tmp_path / "state"
    root.mkdir()
    (root / "baselines").symlink_to(outside, target_is_directory=True)
    repo = ArtifactRepository(root)

    for malicious in ("../../bl_target", "/tmp/bl_target", "target", "bl_../target"):
        assert repo.remove_baseline(malicious) is RemoveStatus.REJECTED
        assert repo.load_baseline(malicious).reason_code == "BASELINE_ID_INVALID"
    assert repo.remove_baseline("bl_target") is RemoveStatus.REJECTED
    assert repo.load_baseline("bl_target").reason_code == "SYMLINK_REJECTED"
    assert target.exists()


def test_observation_load_latest_and_symlink(tmp_path: Path) -> None:
    repo = ArtifactRepository(tmp_path)
    observation = _observation()
    assert repo.load_observation(tmp_path / "missing.json").status is LoadStatus.NOT_FOUND
    assert isinstance(repo.persist_observation(observation), PersistSuccess)
    path = (
        tmp_path
        / "observations"
        / str(observation.installation_id)
        / f"{observation.observation_id}.json"
    )
    assert repo.load_observation(path).observation == observation
    assert len(repo.latest_observations()) == 1
    bad = path.with_name("obs_bad.json")
    bad.write_text("[]")
    assert repo.load_observation(bad).status is LoadStatus.INVALID
    link = path.with_name("obs_link.json")
    link.symlink_to(path)
    assert repo.load_observation(link).reason_code == "SYMLINK_REJECTED"


def test_prune_wrap_records_removes_old_files_and_ignores_invalid_entries(tmp_path: Path) -> None:
    repo = ArtifactRepository(tmp_path)
    record = _wrap()
    installation = tmp_path / "wrap" / str(record.installation_id)
    old = installation / (record.ts.date() - timedelta(days=40)).isoformat()
    old.mkdir(parents=True)
    (old / "stale.json").write_text("{}")
    (old / "keep.txt").write_text("x")
    (installation / "not-a-date").mkdir()
    (installation / "2020-01-01").symlink_to(old, target_is_directory=True)
    assert isinstance(repo.persist_wrap_record(record), PersistSuccess)
    assert not (old / "stale.json").exists()
    assert old.exists()  # non-JSON content prevents unsafe directory removal
    assert (installation / "not-a-date").exists()
