from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from panopticon.release import PAYLOADS, assemble_release


def _assets(root: Path) -> None:
    for name in PAYLOADS:
        (root / name).write_bytes(name.encode())
        (root / f"{name}.cdx.json").write_text('{"bomFormat":"CycloneDX"}\n')


def test_release_manifest_is_deterministic_and_complete(tmp_path: Path) -> None:
    _assets(tmp_path)

    first = assemble_release(tmp_path, "a" * 40)
    second = assemble_release(tmp_path, "a" * 40)

    assert second == first
    assert first.manifest["version"] == "1.0.0"
    checksums = first.checksums.splitlines()
    assert len(checksums) == 12
    for line in checksums:
        digest, name = line.split("  ", 1)
        assert digest == hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()


def test_release_manifest_rejects_missing_assets_and_bad_commit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="INVALID_RELEASE_COMMIT"):
        assemble_release(tmp_path, "main")
    with pytest.raises(ValueError, match="MISSING_RELEASE_ASSETS"):
        assemble_release(tmp_path, "a" * 40)
