"""Create deterministic release archive bytes around one native executable."""

from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

_ARCHIVE_FILES = ("LICENSE", "THIRD_PARTY_NOTICES.md")


def _add_bytes(archive: tarfile.TarFile, name: str, payload: bytes, mode: int) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mode = mode
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    archive.addfile(info, io.BytesIO(payload))


def build_binary_archive(root: Path, binary: Path, target: str) -> bytes:
    if not binary.is_file() or not target or "/" in target or ".." in target:
        raise ValueError("INVALID_BINARY_ARCHIVE_INPUT")
    prefix = f"panopticon-1.0.0-{target}"
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        _add_bytes(archive, f"{prefix}/pano", binary.read_bytes(), 0o755)
        for name in _ARCHIVE_FILES:
            source = root / name
            _add_bytes(archive, f"{prefix}/{name}", source.read_bytes(), 0o644)
    output = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
        compressed.write(tar_buffer.getvalue())
    return output.getvalue()
