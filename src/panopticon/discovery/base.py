"""ClientAdapter contract. See panopticon-buildplan.md §5."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from panopticon.models import ConfigPath, ConfigScope, JsonPointer
from panopticon.util.jsonc.document import JsonValue


class DiscoveryStatus(StrEnum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    PARSE_ERROR = "PARSE_ERROR"
    PERMISSION = "PERMISSION"


@dataclass(frozen=True, slots=True)
class DiscoveryEnv:
    home: Path
    cwd: Path
    os: str  # "darwin" | "linux" | "windows"
    env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceLocation:
    line: int
    column: int
    offset: int


@dataclass(frozen=True, slots=True)
class RawServerEntry:
    name: str
    raw: Mapping[str, JsonValue]
    scope: ConfigScope
    config_path: Path
    logical_path: ConfigPath
    realpath: Path
    original_sha256: str
    json_pointer: JsonPointer
    source_location: SourceLocation
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParseError:
    path: Path
    reason: str
    line: int | None = None
    column: int | None = None
    offset: int | None = None


@dataclass(frozen=True, slots=True)
class ParseResult:
    status: DiscoveryStatus
    entries: list[RawServerEntry] = field(default_factory=list)
    error: ParseError | None = None


class ClientAdapter(Protocol):
    name: str

    def candidate_paths(self, env: DiscoveryEnv) -> list[Path]: ...

    def parse(self, path: Path) -> ParseResult: ...

    def write(self, path: Path, entries: list[RawServerEntry]) -> None:
        """Only `fix/` and `install/` may call this. Must preserve comments and formatting."""
        ...
