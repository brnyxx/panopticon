"""Validate and hash the exact build-once v1.0.0 release asset set."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

PAYLOADS = (
    "panopticon_mcp-1.0.0-py3-none-any.whl",
    "panopticon_mcp-1.0.0.tar.gz",
    "panopticon-1.0.0-linux-x86_64.tar.gz",
    "panopticon-1.0.0-linux-arm64.tar.gz",
    "panopticon-1.0.0-darwin-x86_64.tar.gz",
    "panopticon-1.0.0-darwin-arm64.tar.gz",
)
_SBOMS = tuple(f"{name}.cdx.json" for name in PAYLOADS)
_COMMIT = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True, slots=True)
class ReleaseAssembly:
    manifest: dict[str, object]
    manifest_bytes: bytes
    checksums: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assemble_release(assets: Path, commit: str) -> ReleaseAssembly:
    if _COMMIT.fullmatch(commit) is None:
        raise ValueError("INVALID_RELEASE_COMMIT")
    required = (*PAYLOADS, *_SBOMS)
    missing = [name for name in required if not (assets / name).is_file()]
    if missing:
        raise ValueError("MISSING_RELEASE_ASSETS:" + ",".join(missing))
    hashes = {name: _sha256(assets / name) for name in sorted(required)}
    checksums = "".join(f"{digest}  {name}\n" for name, digest in hashes.items())
    manifest: dict[str, object] = {
        "schema_version": 1,
        "version": "1.0.0",
        "commit": commit,
        "assets": hashes,
    }
    manifest_bytes = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return ReleaseAssembly(manifest, manifest_bytes, checksums)
