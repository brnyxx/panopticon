from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from panopticon.release import assemble_release, payload_names

VERSION = "1.0.1"


def _assets(root: Path) -> None:
    for name in payload_names(VERSION):
        (root / name).write_bytes(name.encode())
        (root / f"{name}.cdx.json").write_text('{"bomFormat":"CycloneDX"}\n')


def test_release_manifest_is_deterministic_and_complete(tmp_path: Path) -> None:
    _assets(tmp_path)

    first = assemble_release(tmp_path, "a" * 40, VERSION)
    second = assemble_release(tmp_path, "a" * 40, VERSION)

    assert second == first
    assert first.manifest["version"] == VERSION
    checksums = first.checksums.splitlines()
    assert len(checksums) == 12
    for line in checksums:
        digest, name = line.split("  ", 1)
        assert digest == hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()


def test_release_manifest_rejects_missing_assets_and_bad_commit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="INVALID_RELEASE_COMMIT"):
        assemble_release(tmp_path, "main", VERSION)
    with pytest.raises(ValueError, match="MISSING_RELEASE_ASSETS"):
        assemble_release(tmp_path, "a" * 40, VERSION)


def test_release_manifest_rejects_unexpected_assets(tmp_path: Path) -> None:
    _assets(tmp_path)
    (tmp_path / "unexpected.bin").write_bytes(b"unexpected")

    with pytest.raises(ValueError, match="RELEASE_ASSET_SET_MISMATCH"):
        assemble_release(tmp_path, "a" * 40, VERSION)


@pytest.mark.parametrize("version", ("1.0", "v1.0.1", "1.0.1rc1", "01.0.1"))
def test_release_manifest_rejects_invalid_stable_versions(tmp_path: Path, version: str) -> None:
    with pytest.raises(ValueError, match="INVALID_RELEASE_VERSION"):
        assemble_release(tmp_path, "a" * 40, version)
