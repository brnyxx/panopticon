"""Validate and hash the exact release asset set."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

_VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
_COMMIT = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True, slots=True)
class ReleaseAssembly:
    manifest: dict[str, object]
    manifest_bytes: bytes
    checksums: str


def validate_version(version: str) -> str:
    if _VERSION.fullmatch(version) is None:
        raise ValueError("INVALID_RELEASE_VERSION")
    return version


def payload_names(version: str) -> tuple[str, ...]:
    version = validate_version(version)
    return (
        f"panopticon_mcp-{version}-py3-none-any.whl",
        f"panopticon_mcp-{version}.tar.gz",
        f"panopticon-{version}-linux-x86_64.tar.gz",
        f"panopticon-{version}-linux-arm64.tar.gz",
        f"panopticon-{version}-darwin-x86_64.tar.gz",
        f"panopticon-{version}-darwin-arm64.tar.gz",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assemble_release(assets: Path, commit: str, version: str) -> ReleaseAssembly:
    if _COMMIT.fullmatch(commit) is None:
        raise ValueError("INVALID_RELEASE_COMMIT")
    version = validate_version(version)
    payloads = payload_names(version)
    required = (*payloads, *(f"{name}.cdx.json" for name in payloads))
    missing = [name for name in required if not (assets / name).is_file()]
    if missing:
        raise ValueError("MISSING_RELEASE_ASSETS:" + ",".join(missing))
    actual = {path.name for path in assets.iterdir() if path.is_file()}
    if actual != set(required):
        raise ValueError("RELEASE_ASSET_SET_MISMATCH")
    hashes = {name: _sha256(assets / name) for name in sorted(required)}
    checksums = "".join(f"{digest}  {name}\n" for name, digest in hashes.items())
    manifest: dict[str, object] = {
        "schema_version": 1,
        "version": version,
        "commit": commit,
        "assets": hashes,
    }
    manifest_bytes = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return ReleaseAssembly(manifest, manifest_bytes, checksums)
