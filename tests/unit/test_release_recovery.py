"""Unit coverage for fail-closed recovery verification."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
recovery = importlib.import_module("verify_release_recovery")
bundle_files = recovery.bundle_files
missing_index_assets = recovery.missing_index_assets
pypi_assets = recovery.pypi_assets
release_assets = recovery.release_assets
prepare_release_metadata = recovery.prepare_release_metadata
signed_files = recovery.signed_files
stage_missing_index_assets = recovery.stage_missing_index_assets
validate_inputs = recovery.validate_inputs
verify_bundle = recovery.verify_bundle
verify_dist = recovery.verify_dist
verify_index = recovery.verify_index
verify_recovery = recovery.verify_recovery
verify_release_state = recovery.verify_release_state
verify_run_jobs = recovery.verify_run_jobs
verify_run_metadata = recovery.verify_run_metadata

SHA = "a" * 40
RUN_ID = "33242971985"
VERSION = "1.0.1"
_SIGSTORE = {
    "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
    "verificationMaterial": {},
    "messageSignature": {},
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pypi_assets() -> frozenset[str]:
    return pypi_assets(VERSION)


def _release_assets() -> frozenset[str]:
    return release_assets(VERSION)


def _bundle_files() -> frozenset[str]:
    return bundle_files(VERSION)


def _bundle(root: Path, commit: str = SHA) -> tuple[Path, dict[str, str]]:
    bundle = root / "bundle"
    bundle.mkdir(parents=True)
    hashes: dict[str, str] = {}
    for name in sorted(_release_assets()):
        path = bundle / name
        path.write_bytes(f"artifact:{name}".encode())
        hashes[name] = _digest(path)
    (bundle / "SHA256SUMS").write_text(
        "".join(f"{hashes[name]}  {name}\n" for name in sorted(hashes)),
        encoding="utf-8",
    )
    (bundle / "release-manifest.json").write_text(
        json.dumps(
            {
                "assets": hashes,
                "commit": commit,
                "schema_version": 1,
                "version": VERSION,
            }
        ),
        encoding="utf-8",
    )
    for name in signed_files(VERSION):
        (bundle / f"{name}.sigstore.json").write_text(
            json.dumps(_SIGSTORE),
            encoding="utf-8",
        )
    assert {path.name for path in bundle.iterdir()} == _bundle_files()
    return bundle, hashes


def _dist(root: Path, bundle: Path) -> Path:
    dist = root / "dist"
    dist.mkdir()
    for name in _pypi_assets():
        (dist / name).write_bytes((bundle / name).read_bytes())
    return dist


def _index(dist: Path) -> dict[str, object]:
    return {
        "urls": [
            {"filename": name, "digests": {"sha256": _digest(dist / name)}}
            for name in sorted(_pypi_assets())
        ]
    }


def _release(bundle: Path, *, draft: bool = True) -> dict[str, object]:
    return {
        "target_commitish": SHA,
        "draft": draft,
        "prerelease": draft,
        "assets": {path.name: _digest(path) for path in bundle.iterdir()},
    }


def _release_list(bundle: Path) -> list[dict[str, object]]:
    return [
        {
            "tag_name": f"v{VERSION}",
            "target_commitish": SHA,
            "draft": True,
            "prerelease": True,
            "assets": [
                {
                    "id": index,
                    "name": path.name,
                    "digest": f"sha256:{_digest(path)}",
                }
                for index, path in enumerate(sorted(bundle.iterdir()), start=1)
            ],
        }
    ]


def _run() -> dict[str, object]:
    return {
        "id": int(RUN_ID),
        "conclusion": "success",
        "head_sha": SHA,
        "event": "workflow_dispatch",
        "path": ".github/workflows/release.yml",
        "name": "release",
        "jobs": [
            {"name": name, "conclusion": "success"}
            for name in (
                "quality",
                "python-package",
                "assemble",
                "verify-images",
                "testpypi",
                "draft",
                "binary (ubuntu-24.04, linux-x86_64)",
                "binary (ubuntu-24.04-arm, linux-arm64)",
                "binary (macos-15-intel, darwin-x86_64)",
                "binary (macos-latest, darwin-arm64)",
            )
        ],
    }


def test_valid_recovery_accepts_exact_draft_and_public_state(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    dist = _dist(tmp_path, bundle)
    downloaded = tmp_path / "downloaded"
    downloaded.mkdir()
    for source in bundle.iterdir():
        (downloaded / source.name).write_bytes(source.read_bytes())

    verify_recovery(
        RUN_ID,
        SHA,
        VERSION,
        bundle,
        dist,
        _index(dist),
        _release(bundle),
        downloaded,
        _run(),
    )
    assert verify_release_state(_release(bundle), bundle, SHA, downloaded, VERSION) is True
    assert (
        verify_release_state(_release(bundle, draft=False), bundle, SHA, downloaded, VERSION)
        is False
    )


@pytest.mark.parametrize(
    ("run_id", "sha"),
    [
        ("", SHA),
        ("abc", SHA),
        ("-1", SHA),
        ("1", "A" * 40),
        ("1", "x" * 40),
    ],
)
def test_malformed_inputs_rejected(run_id: str, sha: str) -> None:
    with pytest.raises(ValueError):
        validate_inputs(run_id, sha)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 1),
        ("conclusion", "failure"),
        ("head_sha", "b" * 40),
        ("event", "push"),
        ("path", ".github/workflows/other.yml"),
        ("name", "other"),
    ],
)
def test_run_metadata_mismatch_rejected(field: str, value: object) -> None:
    metadata = {**_run(), field: value}
    with pytest.raises(ValueError):
        verify_run_metadata(metadata, RUN_ID, SHA)


def test_run_jobs_require_complete_rehearsal_channel() -> None:
    verify_run_jobs(_run())
    metadata = _run()
    jobs = metadata["jobs"]
    assert isinstance(jobs, list)
    jobs.pop()
    with pytest.raises(ValueError, match="RUN_CHANNEL_MISMATCH"):
        verify_run_jobs(metadata)

    metadata = _run()
    jobs = metadata["jobs"]
    assert isinstance(jobs, list)
    jobs[0] = {**jobs[0], "conclusion": "failure"}
    with pytest.raises(ValueError, match="RUN_CHANNEL_MISMATCH"):
        verify_run_jobs(metadata)


def test_bundle_rejects_commit_and_missing_signature(
    tmp_path: Path,
) -> None:
    bundle, _ = _bundle(tmp_path / "commit", commit="b" * 40)
    with pytest.raises(ValueError, match="COMMIT"):
        verify_bundle(bundle, SHA, VERSION)

    bundle, _ = _bundle(tmp_path / "missing")
    (bundle / f"{next(iter(_release_assets()))}.sigstore.json").unlink()
    with pytest.raises(ValueError, match="SET"):
        verify_bundle(bundle, SHA, VERSION)


def test_bundle_rejects_version_set_hash_checksum_and_signature_changes(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path / "manifest-version")
    manifest_path = bundle / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = "1.0.0"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="MANIFEST"):
        verify_bundle(bundle, SHA, VERSION)

    bundle, _ = _bundle(tmp_path / "artifact-version")
    (bundle / "panopticon-1.0.0-linux-x86_64.tar.gz").write_bytes(b"wrong version")
    with pytest.raises(ValueError, match="SET"):
        verify_bundle(bundle, SHA, VERSION)

    bundle, _ = _bundle(tmp_path / "requested-version")
    with pytest.raises(ValueError, match="MANIFEST"):
        verify_bundle(bundle, SHA, "1.0.0")

    bundle, _ = _bundle(tmp_path / "hash")
    (bundle / next(iter(_release_assets()))).write_bytes(b"changed")
    with pytest.raises(ValueError, match="HASH"):
        verify_bundle(bundle, SHA, VERSION)

    bundle, _ = _bundle(tmp_path / "sums")
    (bundle / "SHA256SUMS").write_text("0" * 64 + "  unexpected\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256SUMS"):
        verify_bundle(bundle, SHA, VERSION)

    bundle, _ = _bundle(tmp_path / "signature")
    (bundle / "SHA256SUMS.sigstore.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="SIGSTORE"):
        verify_bundle(bundle, SHA, VERSION)

    bundle, _ = _bundle(tmp_path / "extra")
    (bundle / "extra").write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="SET"):
        verify_bundle(bundle, SHA, VERSION)


def test_dist_and_index_require_exact_names_and_hashes(tmp_path: Path) -> None:
    bundle, hashes = _bundle(tmp_path)
    dist = _dist(tmp_path, bundle)
    verify_dist(bundle, dist, VERSION)
    verify_index(_index(dist), dist, VERSION)
    verify_index({name: hashes[name] for name in _pypi_assets()}, dist, VERSION)

    (dist / next(iter(_pypi_assets()))).write_bytes(b"changed")
    with pytest.raises(ValueError, match="DIST"):
        verify_dist(bundle, dist, VERSION)
    with pytest.raises(ValueError, match="INDEX"):
        verify_index(_index(bundle), dist, VERSION)
    (dist / "extra").write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="DIST"):
        verify_dist(bundle, dist, VERSION)


@pytest.mark.parametrize("present", [next(iter(_pypi_assets())), None])
def test_partial_index_stages_only_missing_exact_artifacts(
    tmp_path: Path,
    present: str | None,
) -> None:
    bundle, _ = _bundle(tmp_path)
    dist = _dist(tmp_path, bundle)
    metadata = {} if present is None else {present: _digest(dist / present)}
    expected_missing = _pypi_assets() - ({present} if present is not None else set())

    assert missing_index_assets(metadata, dist, VERSION) == expected_missing
    staged = tmp_path / "staged"
    assert stage_missing_index_assets(metadata, dist, staged, VERSION) == expected_missing
    assert {path.name for path in staged.iterdir()} == expected_missing
    for name in expected_missing:
        assert (staged / name).read_bytes() == (dist / name).read_bytes()
    if present is not None:
        assert present not in {path.name for path in staged.iterdir()}
        assert (dist / present).read_bytes() == (bundle / present).read_bytes()


def test_partial_index_rejects_changed_or_unexpected_existing_files(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    dist = _dist(tmp_path, bundle)
    name = next(iter(_pypi_assets()))
    with pytest.raises(ValueError, match="INDEX"):
        missing_index_assets({name: "0" * 64}, dist, VERSION)
    with pytest.raises(ValueError, match="INDEX"):
        missing_index_assets({"unexpected.whl": "0" * 64}, dist, VERSION)


def test_release_list_prepares_only_exact_sanitized_asset_downloads(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    metadata, downloads = prepare_release_metadata(_release_list(bundle), VERSION)
    assert metadata == _release(bundle)
    assert {name for _, name in downloads} == {path.name for path in bundle.iterdir()}

    releases = _release_list(bundle)
    assets = releases[0]["assets"]
    assert isinstance(assets, list)
    assets[0] = {**assets[0], "name": "../escape"}
    with pytest.raises(ValueError, match="ASSETS"):
        prepare_release_metadata(releases, VERSION)


def test_release_list_rejects_missing_or_duplicate_release(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    with pytest.raises(ValueError, match="UNIQUE"):
        prepare_release_metadata([], VERSION)
    releases = _release_list(bundle)
    with pytest.raises(ValueError, match="UNIQUE"):
        prepare_release_metadata(releases + releases, VERSION)
    assets = releases[0]["assets"]
    assert isinstance(assets, list)
    assets.pop()
    with pytest.raises(ValueError, match="ASSETS"):
        prepare_release_metadata(releases, VERSION)


def test_release_list_rejects_wrong_tag(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    releases = _release_list(bundle)
    releases[0]["tag_name"] = "v1.0.0"
    with pytest.raises(ValueError, match="UNIQUE"):
        prepare_release_metadata(releases, VERSION)


def test_release_rejects_target_state_assets_and_download_mismatches(
    tmp_path: Path,
) -> None:
    bundle, _ = _bundle(tmp_path)
    downloaded = tmp_path / "downloaded"
    downloaded.mkdir()
    for source in bundle.iterdir():
        (downloaded / source.name).write_bytes(source.read_bytes())

    metadata = _release(bundle)
    with pytest.raises(ValueError, match="TARGET"):
        verify_release_state(
            {**metadata, "target_commitish": "b" * 40}, bundle, SHA, downloaded, VERSION
        )
    with pytest.raises(ValueError, match="STATE"):
        verify_release_state({**metadata, "prerelease": False}, bundle, SHA, downloaded, VERSION)
    with pytest.raises(ValueError, match="ASSETS"):
        verify_release_state({**metadata, "assets": {}}, bundle, SHA, downloaded, VERSION)
    (downloaded / next(iter(_release_assets()))).write_bytes(b"changed")
    with pytest.raises(ValueError, match="HASH"):
        verify_release_state(metadata, bundle, SHA, downloaded, VERSION)


@pytest.mark.parametrize("version", ("1.0", "v1.0.1", "1.0.1rc1", "01.0.1"))
def test_recovery_rejects_malformed_version(tmp_path: Path, version: str) -> None:
    bundle, _ = _bundle(tmp_path)
    dist = _dist(tmp_path, bundle)
    downloaded = tmp_path / "downloaded"
    downloaded.mkdir()
    for source in bundle.iterdir():
        (downloaded / source.name).write_bytes(source.read_bytes())

    with pytest.raises(ValueError, match="INVALID_RELEASE_VERSION"):
        verify_recovery(
            RUN_ID,
            SHA,
            version,
            bundle,
            dist,
            _index(dist),
            _release(bundle),
            downloaded,
            _run(),
        )
