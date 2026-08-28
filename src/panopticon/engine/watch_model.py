"""Typed value contracts for dependency-injected watch orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol


class TargetMode(StrEnum):
    NAME = "name"
    ALL = "all"
    SELF = "self"


@dataclass(frozen=True, slots=True)
class TargetSelection:
    mode: TargetMode
    name: str | None = None

    def __post_init__(self) -> None:
        if self.mode is TargetMode.NAME and not self.name:
            raise ValueError("name selection requires name")
        if self.mode is not TargetMode.NAME and self.name is not None:
            raise ValueError("name is only valid for name selection")


@dataclass(frozen=True, slots=True)
class WatchOptions:
    calls: int = 1
    timeout: float = 20.0
    idle: float = 0.0
    args: tuple[str, ...] = ()
    real_env: bool = False
    headers: tuple[str, ...] = ()
    allow_destructive: bool = False
    self_read_only: bool = False
    offline: bool = False
    runtime: str | None = None
    png: bool = False

    def __post_init__(self) -> None:
        if self.calls < 0 or self.timeout <= 0 or self.idle < 0:
            raise ValueError("invalid watch limits")
        if self.real_env and self.self_read_only:
            raise ValueError("real environment and self read-only are exclusive")
        if self.runtime not in {None, "docker", "podman"}:
            raise ValueError("unsupported watch runtime")


@dataclass(frozen=True, slots=True)
class WatchRequest:
    selection: TargetSelection
    options: WatchOptions = field(default_factory=WatchOptions)


class Coverage(StrEnum):
    COMPLETE = "COMPLETE"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"


class WatchTarget(Protocol):
    name: str
    transport: str
    command: str | None
    args: tuple[str, ...]
    url: str | None


class Evidence(Protocol):
    """Opaque evidence value exchanged between injected stages."""


class PersistenceCandidate(Protocol):
    """Opaque, already-sanitized candidate for persistence."""


@dataclass(frozen=True, slots=True)
class WatchOutcome:
    target: str
    status: str
    reason: str
    coverage: Mapping[str, Coverage] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()
    findings: tuple[PersistenceCandidate, ...] = ()
    persistence: tuple[PersistenceCandidate, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "coverage", MappingProxyType(dict(self.coverage)))


class Inventory(Protocol):
    def select(self, selection: TargetSelection) -> tuple[WatchTarget, ...]: ...


__all__ = [
    "Coverage",
    "Evidence",
    "Inventory",
    "PersistenceCandidate",
    "TargetMode",
    "TargetSelection",
    "WatchOptions",
    "WatchOutcome",
    "WatchRequest",
    "WatchTarget",
]
