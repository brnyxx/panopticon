"""Verify exact and adapted MCP-Sentinel provenance against a clean pinned clone."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

FULL_COMMIT = "e717e955210b1d2a3e9fb1cdc266587c77ffebf3"
REQUIRED_HEADER = "# Copyright (c) 2026 MCP Sentinel contributors\n# SPDX-License-Identifier: MIT\n"


def _git(clone: Path, *args: str, binary: bool = False) -> str | bytes:
    completed = subprocess.run(
        ["git", "-C", str(clone), *args],
        check=True,
        capture_output=True,
    )
    return completed.stdout if binary else completed.stdout.decode().strip()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return value


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a string array")
    return tuple(value)


def _destination(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("manifest destination must be non-empty")
    destination = (root / value).resolve()
    if not destination.is_relative_to(root.resolve()):
        raise ValueError("manifest destination escapes repository")
    return destination


def verify(
    repository: Path,
    clone: Path,
    manifest_path: Path,
    commit: str,
) -> tuple[str, ...]:
    repository = repository.resolve()
    clone = clone.resolve()
    manifest_path = manifest_path.resolve()
    resolved = _git(clone, "rev-parse", f"{commit}^{{commit}}")
    if resolved != FULL_COMMIT:
        return ("UPSTREAM_COMMIT_MISMATCH",)
    if _git(clone, "rev-parse", "HEAD") != FULL_COMMIT:
        return ("UPSTREAM_HEAD_MISMATCH",)
    if _git(clone, "status", "--porcelain"):
        return ("UPSTREAM_CLONE_DIRTY",)
    raw_manifest: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = _mapping(raw_manifest, "manifest")
    if manifest.get("schema_version") != 1:
        return ("MANIFEST_SCHEMA_UNSUPPORTED",)
    upstream = _mapping(manifest.get("upstream"), "upstream")
    if upstream.get("commit") != FULL_COMMIT or upstream.get("license") != "MIT":
        return ("MANIFEST_UPSTREAM_MISMATCH",)
    errors: list[str] = []
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ValueError("files must be an array")
    destinations: set[str] = set()
    exact_destinations: set[str] = set()
    for raw_entry in entries:
        entry = _mapping(raw_entry, "file entry")
        destination_value = entry.get("destination")
        destination = _destination(repository, destination_value)
        destination_name = destination.relative_to(repository).as_posix()
        if destination_name in destinations:
            errors.append(f"DUPLICATE_DESTINATION:{destination_name}")
            continue
        destinations.add(destination_name)
        if destination.is_symlink() or not destination.is_file():
            errors.append(f"DESTINATION_MISSING:{destination_name}")
            continue
        destination_bytes = destination.read_bytes()
        if _sha256(destination_bytes) != entry.get("destination_sha256"):
            errors.append(f"DESTINATION_HASH_MISMATCH:{destination_name}")
        if entry.get("license") != "MIT":
            errors.append(f"LICENSE_MISMATCH:{destination_name}")
        sources = entry.get("sources")
        if not isinstance(sources, list) or not sources:
            errors.append(f"SOURCE_LIST_INVALID:{destination_name}")
            continue
        source_blobs: list[bytes] = []
        for raw_source in sources:
            source = _mapping(raw_source, "source entry")
            source_path = source.get("path")
            if not isinstance(source_path, str) or source_path.startswith(("/", "../")):
                errors.append(f"SOURCE_PATH_INVALID:{destination_name}")
                continue
            blob = _git(clone, "show", f"{FULL_COMMIT}:{source_path}", binary=True)
            if not isinstance(blob, bytes):
                raise TypeError("binary git output expected")
            source_blobs.append(blob)
            if _sha256(blob) != source.get("sha256"):
                errors.append(f"SOURCE_HASH_MISMATCH:{destination_name}:{source_path}")
        mode = entry.get("mode")
        if mode == "exact":
            exact_destinations.add(destination_name)
            if len(source_blobs) != 1 or destination_bytes != source_blobs[0]:
                errors.append(f"EXACT_CONTENT_MISMATCH:{destination_name}")
        elif mode == "adapted":
            if not destination_bytes.startswith(REQUIRED_HEADER.encode()):
                errors.append(f"ADAPTED_HEADER_MISSING:{destination_name}")
            transform = entry.get("transform")
            if not isinstance(transform, str) or not transform:
                errors.append(f"ADAPTED_TRANSFORM_MISSING:{destination_name}")
        else:
            errors.append(f"MODE_INVALID:{destination_name}")
    roots = _strings(manifest.get("exact_roots"), "exact_roots")
    actual_exact: set[str] = set()
    for root_name in roots:
        root = _destination(repository, root_name)
        if not root.is_dir():
            errors.append(f"EXACT_ROOT_MISSING:{root_name}")
            continue
        actual_exact.update(
            path.relative_to(repository).as_posix()
            for path in root.rglob("*")
            if path.is_file() and not path.is_symlink()
        )
    for singleton in _strings(manifest.get("exact_files"), "exact_files"):
        actual_exact.add(_destination(repository, singleton).relative_to(repository).as_posix())
    if actual_exact != exact_destinations:
        errors.append("EXACT_MANIFEST_CLOSURE_MISMATCH")
    tests = _mapping(manifest.get("tests"), "tests")
    nodeids = _strings(tests.get("nodeids"), "tests.nodeids")
    if tests.get("expected_count") != 125 or len(nodeids) != 125 or len(set(nodeids)) != 125:
        errors.append("UPSTREAM_TEST_COUNT_MISMATCH")
    notice_value = manifest.get("notice")
    notice = _destination(repository, notice_value)
    if not notice.is_file() or FULL_COMMIT not in notice.read_text(encoding="utf-8"):
        errors.append("NOTICE_MISSING")
    return tuple(sorted(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-clone", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("vendor/mcp-sentinel-e717e955.json"),
    )
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    errors = verify(
        arguments.repository,
        arguments.source_clone,
        arguments.manifest,
        arguments.commit,
    )
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"verified MCP-Sentinel provenance at {FULL_COMMIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
