from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

import pytest

from panopticon.release import build_binary_archive


def test_binary_archive_is_deterministic_and_portable(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "LICENSE").write_text("license\n", encoding="utf-8")
    (root / "THIRD_PARTY_NOTICES.md").write_text("notices\n", encoding="utf-8")
    binary = root / "pano"
    binary.write_bytes(b"executable")
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"

    first.write_bytes(build_binary_archive(root, binary, "linux-x86_64"))
    second.write_bytes(build_binary_archive(root, binary, "linux-x86_64"))

    assert first.read_bytes() == second.read_bytes()
    tar_payload = gzip.decompress(first.read_bytes())
    with tarfile.open(fileobj=io.BytesIO(tar_payload), mode="r:") as archive:
        members = archive.getmembers()
        assert [member.name for member in members] == [
            "panopticon-1.0.0-linux-x86_64/pano",
            "panopticon-1.0.0-linux-x86_64/LICENSE",
            "panopticon-1.0.0-linux-x86_64/THIRD_PARTY_NOTICES.md",
        ]
        assert members[0].mode == 0o755
        assert all(member.mtime == 0 for member in members)


def test_binary_archive_rejects_untrusted_target(tmp_path: Path) -> None:
    binary = tmp_path / "pano"
    binary.write_bytes(b"executable")

    with pytest.raises(ValueError, match="INVALID_BINARY_ARCHIVE_INPUT"):
        build_binary_archive(tmp_path, binary, "../escape")
