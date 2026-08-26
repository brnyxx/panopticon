"""ClientAdapter contract. See docs/PLAN.md §5."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol


class DiscoveryStatus(StrEnum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    PARSE_ERROR = "PARSE_ERROR"
    PERMISSION = "PERMISSION"


@dataclass(frozen=True)
class DiscoveryEnv:
    home: Path
    cwd: Path
    os: str  # "darwin" | "linux" | "windows"
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RawServerEntry:
    name: str
    raw: dict[str, Any]
    scope: str  # "global" | "project"
    config_path: Path


@dataclass(frozen=True)
class ParseError:
    path: Path
    reason: str
    line: int | None = None


@dataclass(frozen=True)
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
