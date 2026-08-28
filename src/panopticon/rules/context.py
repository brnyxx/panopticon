"""Typed inputs supplied to rules; rules never read external state directly."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum, unique
from typing import Generic, TypeVar

T = TypeVar("T")


@unique
class SourceStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNKNOWN = "UNKNOWN"
    INCOMPLETE = "INCOMPLETE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class SourceState(Generic[T]):
    status: SourceStatus
    value: T | None = None
    reason: str | None = None

    @classmethod
    def available(cls, value: T) -> SourceState[T]:
        return cls(SourceStatus.AVAILABLE, value)

    @classmethod
    def unknown(cls, reason: str = "UNKNOWN") -> SourceState[T]:
        return cls(SourceStatus.UNKNOWN, None, reason)

    @classmethod
    def incomplete(cls, reason: str = "INCOMPLETE") -> SourceState[T]:
        return cls(SourceStatus.INCOMPLETE, None, reason)

    @classmethod
    def unsupported(cls, reason: str = "UNSUPPORTED") -> SourceState[T]:
        return cls(SourceStatus.UNSUPPORTED, None, reason)


@dataclass(frozen=True, slots=True)
class RuleContext:
    inventory: SourceState[object] = field(default_factory=SourceState.unknown)
    observation: SourceState[object] = field(default_factory=SourceState.unknown)
    declared: SourceState[object] = field(default_factory=SourceState.unknown)
    history: SourceState[object] = field(default_factory=SourceState.unknown)
    config: SourceState[object] = field(default_factory=SourceState.unknown)
    allowlist: SourceState[object] = field(default_factory=SourceState.unknown)
    previous_baseline: SourceState[object] = field(default_factory=SourceState.unknown)

    @classmethod
    def empty(cls) -> RuleContext:
        state: SourceState[object] = SourceState.unknown()
        return cls(state, state, state, state, state, state, state)
