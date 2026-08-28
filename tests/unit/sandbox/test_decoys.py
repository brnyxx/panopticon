from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from panopticon.sandbox.decoy import decoy_archive, generate_decoy_home, marker_encodings
from panopticon.sandbox.matcher import DecoyMatcher


def test_deterministic_archive_build_and_variant_matching() -> None:
    filenames = ("src/server.py", ".env.example", "docs/guide.txt")
    first = generate_decoy_home("fixture-seed", "installation", project_filenames=filenames)
    second = generate_decoy_home("fixture-seed", "installation", project_filenames=filenames)

    first_archive = decoy_archive(first)
    second_archive = decoy_archive(second)

    assert first == second
    assert first_archive == second_archive
    assert len(first.env) == 30
    assert first.files["project/src/server.py"] == b""
    assert first.files["project/.env.example"]
    with tarfile.open(fileobj=io.BytesIO(first_archive), mode="r:") as archive:
        assert "project/src/server.py" in archive.getnames()
        assert ".ssh/id_ed25519" in archive.getnames()
        assert ".config/google-chrome/Default/Cookies" in archive.getnames()

    chunks: list[bytes] = []
    expected: set[tuple[str, str]] = set()
    for marker in first.markers:
        for encoded, variant in marker_encodings(marker):
            chunks.extend((encoded[:3], encoded[3:], b"\n"))
            expected.add((marker.key, variant))
    report = DecoyMatcher(first, max_bytes=2_000_000).match(chunks)

    observed = {(match.marker.key, match.variant) for match in report.matches}
    assert expected <= observed
    assert report.coverage == "COMPLETE"


def test_project_filenames_reject_absolute_and_parent_paths() -> None:
    for value in (str(Path.home() / "secret"), "../secret", "folder/../../secret"):
        with pytest.raises(ValueError):
            generate_decoy_home("seed", project_filenames=(value,))
