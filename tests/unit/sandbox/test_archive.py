from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from panopticon.sandbox.archive import archive_for_copy
from panopticon.sandbox.base import SandboxError


def test_archive_is_deterministic_and_canonical(tmp_path: Path) -> None:
    source = tmp_path / "decoy"
    source.mkdir()
    (source / "token.txt").write_text("synthetic")

    first = archive_for_copy(source)
    second = archive_for_copy(source)

    assert first == second
    with tarfile.open(fileobj=io.BytesIO(first), mode="r:") as archive:
        member = archive.getmember("token.txt")
        assert member.uid == 1000
        assert member.gid == 1000
        assert member.mtime == 0


def test_archive_rejects_symbolic_links(tmp_path: Path) -> None:
    source = tmp_path / "decoy"
    source.mkdir()
    (source / "link").symlink_to(tmp_path / "outside")

    with pytest.raises(SandboxError, match="COPY_SOURCE_SYMLINK"):
        archive_for_copy(source)
