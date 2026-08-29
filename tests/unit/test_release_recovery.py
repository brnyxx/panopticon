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
PYPI_ASSETS = recovery.PYPI_ASSETS
RELEASE_ASSETS = recovery.RELEASE_ASSETS
missing_index_assets = recovery.missing_index_assets
prepare_release_metadata = recovery.prepare_release_metadata
stage_missing_index_assets = recovery.stage_missing_index_assets
validate_inputs = recovery.validate_inputs
verify_bundle = recovery.verify_bundle
verify_dist = recovery.verify_dist
verify_index = recovery.verify_index
verify_recovery = recovery.verify_recovery
verify_release_state = recovery.verify_release_state
verify_run_metadata = recovery.verify_run_metadata

SHA = "a" * 40
RUN_ID = "33242971985"
_SIGSTORE = {
    "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
    "verificationMaterial": {},
    "messageSignature": {},
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle(root: Path, commit: str = SHA) -> tuple[Path, dict[str, str]]:
    bundle = root / "bundle"
    bundle.mkdir(parents=True)
    hashes: dict[str, str] = {}
    for name in sorted(RELEASE_ASSETS):
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
                "version": "1.0.0",
            }
        ),
        encoding="utf-8",
    )
    signed = RELEASE_ASSETS | {"SHA256SUMS", "release-manifest.json"}
    for name in signed:
        (bundle / f"{name}.sigstore.json").write_text(
            json.dumps(_SIGSTORE),
            encoding="utf-8",
        )
    return bundle, hashes


def _dist(root: Path, bundle: Path) -> Path:
    dist = root / "dist"
    dist.mkdir()
    for name in PYPI_ASSETS:
        (dist / name).write_bytes((bundle / name).read_bytes())
    return dist


def _index(dist: Path) -> dict[str, object]:
    return {
        "urls": [
            {"filename": name, "digests": {"sha256": _digest(dist / name)}}
            for name in sorted(PYPI_ASSETS)
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
            "tag_name": "v1.0.0",
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
        bundle,
        dist,
        _index(dist),
        _release(bundle),
        downloaded,
        _run(),
    )
    assert verify_release_state(_release(bundle), bundle, SHA, downloaded) is True
    assert verify_release_state(_release(bundle, draft=False), bundle, SHA, downloaded) is False


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


def test_bundle_rejects_commit_set_hash_checksum_and_signature_changes(
    tmp_path: Path,
) -> None:
    bundle, _ = _bundle(tmp_path / "commit", commit="b" * 40)
    with pytest.raises(ValueError, match="COMMIT"):
        verify_bundle(bundle, SHA)

    bundle, _ = _bundle(tmp_path / "missing")
    (bundle / f"{next(iter(RELEASE_ASSETS))}.sigstore.json").unlink()
    with pytest.raises(ValueError, match="SET"):
        verify_bundle(bundle, SHA)

    bundle, _ = _bundle(tmp_path / "hash")
    (bundle / next(iter(RELEASE_ASSETS))).write_bytes(b"changed")
    with pytest.raises(ValueError, match="HASH"):
        verify_bundle(bundle, SHA)

    bundle, _ = _bundle(tmp_path / "sums")
    (bundle / "SHA256SUMS").write_text("0" * 64 + "  unexpected\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256SUMS"):
        verify_bundle(bundle, SHA)

    bundle, _ = _bundle(tmp_path / "signature")
    (bundle / "SHA256SUMS.sigstore.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="SIGSTORE"):
        verify_bundle(bundle, SHA)

    bundle, _ = _bundle(tmp_path / "extra")
    (bundle / "extra").write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="SET"):
        verify_bundle(bundle, SHA)


def test_dist_and_index_require_exact_names_and_hashes(tmp_path: Path) -> None:
    bundle, hashes = _bundle(tmp_path)
    dist = _dist(tmp_path, bundle)
    verify_dist(bundle, dist)
    verify_index(_index(dist), dist)
    verify_index({name: hashes[name] for name in PYPI_ASSETS}, dist)

    (dist / next(iter(PYPI_ASSETS))).write_bytes(b"changed")
    with pytest.raises(ValueError, match="DIST"):
        verify_dist(bundle, dist)
    with pytest.raises(ValueError, match="INDEX"):
        verify_index(_index(bundle), dist)
    (dist / "extra").write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="DIST"):
        verify_dist(bundle, dist)


@pytest.mark.parametrize("present", [next(iter(PYPI_ASSETS)), None])
def test_partial_index_stages_only_missing_exact_artifacts(
    tmp_path: Path,
    present: str | None,
) -> None:
    bundle, _ = _bundle(tmp_path)
    dist = _dist(tmp_path, bundle)
    metadata = {} if present is None else {present: _digest(dist / present)}
    expected_missing = PYPI_ASSETS - ({present} if present is not None else set())

    assert missing_index_assets(metadata, dist) == expected_missing
    staged = tmp_path / "staged"
    assert stage_missing_index_assets(metadata, dist, staged) == expected_missing
    assert {path.name for path in staged.iterdir()} == expected_missing
    for name in expected_missing:
        assert (staged / name).read_bytes() == (dist / name).read_bytes()


def test_partial_index_rejects_changed_or_unexpected_existing_files(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    dist = _dist(tmp_path, bundle)
    name = next(iter(PYPI_ASSETS))
    with pytest.raises(ValueError, match="INDEX"):
        missing_index_assets({name: "0" * 64}, dist)
    with pytest.raises(ValueError, match="INDEX"):
        missing_index_assets({"unexpected.whl": "0" * 64}, dist)


def test_release_list_prepares_only_exact_sanitized_asset_downloads(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    metadata, downloads = prepare_release_metadata(_release_list(bundle))
    assert metadata == _release(bundle)
    assert {name for _, name in downloads} == {path.name for path in bundle.iterdir()}

    releases = _release_list(bundle)
    assets = releases[0]["assets"]
    assert isinstance(assets, list)
    assets[0] = {**assets[0], "name": "../escape"}
    with pytest.raises(ValueError, match="ASSETS"):
        prepare_release_metadata(releases)


def test_release_list_rejects_missing_or_duplicate_release(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    with pytest.raises(ValueError, match="UNIQUE"):
        prepare_release_metadata([])
    releases = _release_list(bundle)
    with pytest.raises(ValueError, match="UNIQUE"):
        prepare_release_metadata(releases + releases)
    assets = releases[0]["assets"]
    assert isinstance(assets, list)
    assets.pop()
    with pytest.raises(ValueError, match="ASSETS"):
        prepare_release_metadata(releases)


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
        verify_release_state({**metadata, "target_commitish": "b" * 40}, bundle, SHA, downloaded)
    with pytest.raises(ValueError, match="STATE"):
        verify_release_state({**metadata, "prerelease": False}, bundle, SHA, downloaded)
    with pytest.raises(ValueError, match="ASSETS"):
        verify_release_state({**metadata, "assets": {}}, bundle, SHA, downloaded)
    (downloaded / next(iter(RELEASE_ASSETS))).write_bytes(b"changed")
    with pytest.raises(ValueError, match="HASH"):
        verify_release_state(metadata, bundle, SHA, downloaded)
