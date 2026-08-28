"""Immutable source metadata and semantic span contracts for JSONC."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

from panopticon.models import ConfigPath, JsonPointer

JsonValue: TypeAlias = str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """One semantic JSON value or container in the original byte stream."""

    pointer: JsonPointer
    start: int
    end: int
    line: int
    column: int
    offset: int


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """Parsed JSONC value plus immutable source identity and byte spans."""

    value: JsonValue
    original_bytes: bytes
    encoding: str
    bom: bytes
    newline: str
    logical_path: ConfigPath
    path: Path
    realpath: Path
    original_sha256: str
    spans: tuple[SourceSpan, ...]
    _identity: tuple[int, int] | None = field(default=None, repr=False, compare=False)

    @property
    def identity(self) -> tuple[int, int] | None:
        """Return the captured device/inode identity when the path was available."""
        return self._identity


def source_location(source: bytes, offset: int, bom_length: int) -> tuple[int, int]:
    """Return one-based line and column for a byte offset."""
    line = 1
    line_start = 0
    index = 0
    while index < offset:
        if source[index] == 0x0D:
            if index + 1 < offset and source[index + 1] == 0x0A:
                index += 1
            line += 1
            line_start = index + 1
        elif source[index] == 0x0A:
            line += 1
            line_start = index + 1
        index += 1
    if line == 1:
        line_start = bom_length
    return line, max(1, offset - line_start + 1)


def path_identity(path: Path) -> tuple[int, int] | None:
    """Capture a path's lstat identity without following a symlink."""
    try:
        stat_result = os.lstat(path)
    except OSError:
        return None
    return stat_result.st_dev, stat_result.st_ino


def detect_newline(source: bytes) -> str:
    """Return the first supported newline convention present in source bytes."""
    for index, byte in enumerate(source):
        if byte == 0x0D:
            return "\r\n" if index + 1 < len(source) and source[index + 1] == 0x0A else "\r"
        if byte == 0x0A:
            return "\n"
    return "\n"
