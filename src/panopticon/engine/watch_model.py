"""Typed value contracts for dependency-injected watch orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
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

    def __post_init__(self) -> None:
        if self.calls < 0 or self.timeout <= 0 or self.idle < 0:
            raise ValueError("invalid watch limits")
        if self.real_env and self.self_read_only:
            raise ValueError("real environment and self read-only are exclusive")


@dataclass(frozen=True, slots=True)
class WatchRequest:
    selection: TargetSelection
    options: WatchOptions = field(default_factory=WatchOptions)


class Coverage(StrEnum):
    COMPLETE = "COMPLETE"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class WatchOutcome:
    target: str
    status: str
    reason: str
    coverage: Mapping[str, Coverage] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()
    findings: tuple[object, ...] = ()
    persistence: tuple[object, ...] = ()


class Inventory(Protocol):
    def select(self, selection: TargetSelection) -> tuple[object, ...]: ...


__all__ = [
    "Coverage",
    "Inventory",
    "TargetMode",
    "TargetSelection",
    "WatchOptions",
    "WatchOutcome",
    "WatchRequest",
]
