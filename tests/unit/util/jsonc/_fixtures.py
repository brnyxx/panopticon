"""Immutable JSONC test fixtures and operation specifications."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from panopticon.models import ConfigPath

from ._protocols import DocumentLike, JsonValue, PatchLike

JSONC_SOURCE: Final[bytes] = (
    b"\xef\xbb\xbf"
    b"// leading comment must stay\r\n"
    b"{\r\n"
    b'  "unknown": {"keep": "byte-for-byte",}, // untouched member\r\n'
    b'  "mcpServers": {\r\n'
    b'    "fixture": {\r\n'
    b'      "command": "uvx",\r\n'
    b'      "args": ["fixture", "--old",],\r\n'
    b'      "env": {\r\n'
    b'        "TOKEN": "${env:TOKEN}",\r\n'
    b'        "INPUT": "${input:command}",\r\n'
    b'        "ROOT": "${workspaceFolder}",\r\n'
    b"      },\r\n"
    b"    },\r\n"
    b"  },\r\n"
    b"}\r\n"
)
LOGICAL_PATH: Final[ConfigPath] = ConfigPath("~/.config/fixture.jsonc")


@dataclass(frozen=True, slots=True)
class DocumentSpec:
    source: bytes
    path: Path
    logical_path: ConfigPath = LOGICAL_PATH


@dataclass(frozen=True, slots=True)
class PatchSpec:
    operation: str
    pointer: str
    value: JsonValue | None = None


@dataclass(frozen=True, slots=True)
class EditInterval:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class WriteSpec:
    target: Path
    document: DocumentLike
    patches: tuple[PatchLike, ...]


def write_source(path: Path, source: bytes = JSONC_SOURCE) -> None:
    """Create one isolated source fixture under pytest's temporary directory."""
    path.write_bytes(source)
