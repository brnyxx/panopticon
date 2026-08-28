from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from pytest import MonkeyPatch

_SPEC = importlib.util.spec_from_file_location(
    "panopticon_upstream_provenance",
    Path(__file__).resolve().parents[2] / "scripts" / "verify_upstream_provenance.py",
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("provenance verifier could not be loaded")
provenance = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = provenance
_SPEC.loader.exec_module(provenance)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fixture_manifest(root: Path, *, include_adapted: bool = False) -> Path:
    exact = root / "tests" / "upstream" / "src" / "source.py"
    exact.parent.mkdir(parents=True)
    exact.write_bytes(b"exact source\n")
    notice = root / "THIRD_PARTY_NOTICES.md"
    notice.write_text(provenance.FULL_COMMIT, encoding="utf-8")
    entries: list[dict[str, object]] = [
        {
            "destination": "tests/upstream/src/source.py",
            "destination_sha256": digest(exact.read_bytes()),
            "license": "MIT",
            "mode": "exact",
            "role": "replay",
            "sources": [{"path": "source.py", "sha256": digest(b"exact source\n")}],
        }
    ]
    if include_adapted:
        adapted = root / "src" / "panopticon" / "analyzers" / "static" / "adapted.py"
        adapted.parent.mkdir(parents=True)
        adapted.write_text(
            provenance.REQUIRED_HEADER + "VALUE = 1\n",
            encoding="utf-8",
        )
        entries.append(
            {
                "destination": "src/panopticon/analyzers/static/adapted.py",
                "destination_sha256": digest(adapted.read_bytes()),
                "license": "MIT",
                "mode": "adapted",
                "role": "product",
                "sources": [{"path": "source.py", "sha256": digest(b"exact source\n")}],
                "transform": "typed port",
            }
        )
    manifest = {
        "schema_version": 1,
        "upstream": {"commit": provenance.FULL_COMMIT, "license": "MIT"},
        "exact_roots": ["tests/upstream/src"],
        "exact_files": [],
        "files": entries,
        "notice": "THIRD_PARTY_NOTICES.md",
        "tests": {
            "expected_count": 125,
            "nodeids": [f"tests/test_source.py::test_{index}" for index in range(125)],
        },
    }
    manifest_path = root / "vendor.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def fake_git(monkeypatch: MonkeyPatch) -> None:
    def git(_clone: Path, *args: str, binary: bool = False) -> str | bytes:
        if args[:2] == ("rev-parse", "HEAD") or args[0] == "rev-parse":
            return provenance.FULL_COMMIT
        if args[0] == "status":
            return ""
        if args[0] == "show":
            return b"exact source\n" if binary else "exact source"
        raise AssertionError(args)

    monkeypatch.setattr(provenance, "_git", git)


def test_matching_exact_and_adapted_files_pass(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    manifest = fixture_manifest(tmp_path, include_adapted=True)
    fake_git(monkeypatch)

    assert provenance.verify(tmp_path, tmp_path / "clone", manifest, "e717e955") == ()


def test_modified_vendor_file_fails_manifest(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    manifest = fixture_manifest(tmp_path)
    fake_git(monkeypatch)
    (tmp_path / "tests" / "upstream" / "src" / "source.py").write_bytes(b"modified\n")

    errors = provenance.verify(tmp_path, tmp_path / "clone", manifest, "e717e955")

    assert "DESTINATION_HASH_MISMATCH:tests/upstream/src/source.py" in errors
    assert "EXACT_CONTENT_MISMATCH:tests/upstream/src/source.py" in errors


def test_missing_adapted_header_and_duplicate_test_ids_fail(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    manifest_path = fixture_manifest(tmp_path, include_adapted=True)
    fake_git(monkeypatch)
    adapted = tmp_path / "src" / "panopticon" / "analyzers" / "static" / "adapted.py"
    adapted.write_text("VALUE = 1\n", encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][1]["destination_sha256"] = digest(adapted.read_bytes())
    manifest["tests"]["nodeids"][-1] = manifest["tests"]["nodeids"][0]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    errors = provenance.verify(tmp_path, tmp_path / "clone", manifest_path, "e717e955")

    assert "ADAPTED_HEADER_MISSING:src/panopticon/analyzers/static/adapted.py" in errors
    assert "UPSTREAM_TEST_COUNT_MISMATCH" in errors


def test_official_server_manifest_preserves_source_provenance() -> None:
    manifest_path = (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "fixtures"
        / "mcp"
        / "official"
        / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert {entry["name"] for entry in manifest["servers"]} == {
        "filesystem",
        "github",
        "fetch",
        "memory",
        "sqlite",
    }
    expected = {
        "filesystem": "cda92bdaacd558192fedf1a60d2bb27510792388",
        "memory": "cda92bdaacd558192fedf1a60d2bb27510792388",
        "fetch": "cda92bdaacd558192fedf1a60d2bb27510792388",
        "github": "1f705677a930ec618b7a16d87d00cee7db747ff2",
        "sqlite": "1f705677a930ec618b7a16d87d00cee7db747ff2",
    }
    for entry in manifest["servers"]:
        assert entry["commit"] == expected[entry["name"]]
        assert entry["source"].endswith(f"/src/{entry['name']}")
        if entry["status"] == "blocked":
            assert "HTTP 404" not in entry["blocker"]
            assert "npm registry" not in entry["blocker"]
