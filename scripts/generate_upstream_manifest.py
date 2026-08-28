"""Generate the canonical MCP-Sentinel provenance manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from verify_upstream_provenance import FULL_COMMIT

EXACT_ROOTS = (
    "tests/upstream/src",
    "tests/upstream/tests",
    "tests/upstream/scripts",
    "tests/upstream/schemas",
)
EXACT_FILES = (
    "tests/upstream/LICENSE",
    "tests/upstream/action.yml",
    "src/panopticon/analyzers/static/semgrep/sent002.yaml",
    "src/panopticon/analyzers/static/semgrep/sent005.yaml",
)
ADAPTED_SOURCES = {
    "src/panopticon/analyzers/static/__init__.py": ("src/sentinel/static/__init__.py",),
    "src/panopticon/analyzers/static/model.py": ("src/sentinel/static/model.py",),
    "src/panopticon/analyzers/static/ast_utils.py": ("src/sentinel/static/ast_utils.py",),
    "src/panopticon/analyzers/static/traversal.py": ("src/sentinel/static/traversal.py",),
    "src/panopticon/analyzers/static/catalog.py": ("src/sentinel/static/catalog.py",),
    "src/panopticon/analyzers/static/engine.py": ("src/sentinel/static/engine.py",),
    "src/panopticon/analyzers/static/semgrep_adapter.py": (
        "src/sentinel/static/semgrep_adapter.py",
    ),
    "src/panopticon/analyzers/static/rules/__init__.py": ("src/sentinel/static/rules/__init__.py",),
    **{
        f"src/panopticon/analyzers/static/rules/sent{number:03}.py": (
            f"src/sentinel/static/rules/sent{number:03}.py",
        )
        for number in range(1, 8)
    },
    "src/panopticon/analyzers/semantic/model.py": ("src/sentinel/llm/schema.py",),
    "src/panopticon/analyzers/semantic/__init__.py": ("src/sentinel/llm/__init__.py",),
    "src/panopticon/analyzers/semantic/context.py": ("src/sentinel/llm/context.py",),
    "src/panopticon/analyzers/semantic/tools.py": ("src/sentinel/llm/tools.py",),
    "src/panopticon/analyzers/semantic/cache.py": ("src/sentinel/llm/cache.py",),
    "src/panopticon/analyzers/semantic/reviewer.py": ("src/sentinel/llm/semantic_reviewer.py",),
    "src/panopticon/analyzers/dependency/model.py": (
        "src/sentinel/config.py",
        "src/sentinel/dynamic/sandbox.py",
    ),
    "src/panopticon/analyzers/dependency/requirements.py": (
        "src/sentinel/config.py",
        "src/sentinel/dynamic/sandbox.py",
    ),
}


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git_blob(clone: Path, path: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(clone), "show", f"{FULL_COMMIT}:{path}"],
        check=True,
        capture_output=True,
    ).stdout


def _source_path(destination: str) -> str:
    prefix = "tests/upstream/"
    if destination.startswith(prefix):
        return destination.removeprefix(prefix)
    product_prefix = "src/panopticon/analyzers/static/semgrep/"
    if destination.startswith(product_prefix):
        return f"src/sentinel/static/semgrep/{destination.removeprefix(product_prefix)}"
    raise ValueError("exact destination has no upstream mapping")


def _entry(
    root: Path,
    clone: Path,
    destination: str,
    sources: tuple[str, ...],
    mode: str,
    role: str,
) -> dict[str, object]:
    destination_bytes = (root / destination).read_bytes()
    return {
        "destination": destination,
        "destination_sha256": _sha256(destination_bytes),
        "license": "MIT",
        "mode": mode,
        "role": role,
        "sources": [
            {"path": source, "sha256": _sha256(_git_blob(clone, source))} for source in sources
        ],
        **(
            {"transform": "Typed Panopticon port preserving pinned business conditions"}
            if mode == "adapted"
            else {}
        ),
    }


def _nodeids(replay: Path) -> tuple[str, ...]:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(replay / "pytest.ini"),
            "--collect-only",
            "-q",
            str(replay / "tests"),
        ],
        cwd=replay,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return tuple(
        line.strip()
        for line in completed.stdout.splitlines()
        if "::test_" in line and not line.startswith(("<", "="))
    )


def generate(root: Path, clone: Path) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    for root_name in EXACT_ROOTS:
        for destination in sorted(path for path in (root / root_name).rglob("*") if path.is_file()):
            relative = destination.relative_to(root).as_posix()
            entries.append(
                _entry(root, clone, relative, (_source_path(relative),), "exact", "replay")
            )
    for relative in EXACT_FILES:
        entries.append(_entry(root, clone, relative, (_source_path(relative),), "exact", "replay"))
    for destination, sources in sorted(ADAPTED_SOURCES.items()):
        if (root / destination).is_file():
            entries.append(_entry(root, clone, destination, sources, "adapted", "product"))
    license_bytes = _git_blob(clone, "LICENSE")
    nodeids = _nodeids(root / "tests" / "upstream")
    return {
        "schema_version": 1,
        "upstream": {
            "commit": FULL_COMMIT,
            "license": "MIT",
            "license_path": "LICENSE",
            "license_sha256": _sha256(license_bytes),
            "repository": "https://github.com/BashaarJavaid/MCP-Sentinel",
        },
        "exact_roots": list(EXACT_ROOTS),
        "exact_files": list(EXACT_FILES),
        "files": sorted(entries, key=lambda entry: str(entry["destination"])),
        "notice": "THIRD_PARTY_NOTICES.md",
        "tests": {"expected_count": 125, "nodeids": list(nodeids)},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-clone", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("vendor/mcp-sentinel-e717e955.json"),
    )
    arguments = parser.parse_args()
    root = Path.cwd().resolve()
    manifest = generate(root, arguments.source_clone.resolve())
    tests = manifest.get("tests")
    if not isinstance(tests, dict):
        raise TypeError("generated tests manifest must be an object")
    nodeids = tests.get("nodeids")
    if tests.get("expected_count") != 125 or not isinstance(nodeids, list) or len(nodeids) != 125:
        raise ValueError("upstream test collection count changed")
    output = arguments.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
