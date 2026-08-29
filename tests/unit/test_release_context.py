from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
release_context = importlib.import_module("release_context")


def test_release_context_reads_canonical_package_version(tmp_path: Path) -> None:
    output = tmp_path / "github-output"

    release_context.main_for_output(output)

    assert output.read_text(encoding="utf-8") == (
        "version=1.0.1\ntag=v1.0.1\nbundle_name=release-bundle-1.0.1\n"
    )


def test_release_context_requires_existing_parent(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="GITHUB_OUTPUT_PARENT_MISSING"):
        release_context.main_for_output(tmp_path / "missing" / "github-output")
