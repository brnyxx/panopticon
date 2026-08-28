"""Deterministic in-memory archives for container copy-in."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

from panopticon.sandbox.base import SandboxError

MAX_ARCHIVE_BYTES = 32 * 1024 * 1024


def _canonical(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 1000
    info.gid = 1000
    info.uname = "pano"
    info.gname = "pano"
    info.mtime = 0
    info.mode = 0o700 if info.isdir() else 0o600
    return info


def archive_for_copy(source: Path) -> bytes:
    """Return a bounded canonical tar without following symbolic links."""
    if not source.exists() or source.is_symlink():
        raise SandboxError("COPY_SOURCE_INVALID")
    members = (
        sorted(source.rglob("*"), key=lambda path: path.relative_to(source).as_posix())
        if source.is_dir()
        else [source]
    )
    if any(member.is_symlink() for member in members):
        raise SandboxError("COPY_SOURCE_SYMLINK")
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for member in members:
            name = member.relative_to(source).as_posix() if source.is_dir() else member.name
            archive.add(member, arcname=name, recursive=False, filter=_canonical)
            if output.tell() > MAX_ARCHIVE_BYTES:
                raise SandboxError("COPY_SOURCE_TOO_LARGE")
    payload = output.getvalue()
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise SandboxError("COPY_SOURCE_TOO_LARGE")
    return payload
