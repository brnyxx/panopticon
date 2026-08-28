"""Remote observer boundary. Remote file/process evidence is never inferred."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from .watch_model import Evidence


@dataclass(frozen=True, slots=True)
class RemoteTarget:
    name: str
    endpoint: str
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))


@dataclass(frozen=True, slots=True)
class RemoteRun:
    status: str
    reason: str
    payload: Evidence | None = field(default=None, repr=False)
    coverage: Mapping[str, str] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "coverage", MappingProxyType(dict(self.coverage)))


class RemoteObserver(Protocol):
    def observe(
        self,
        target: RemoteTarget,
        *,
        calls: int,
        timeout: float,
        idle: float,
        headers: Mapping[str, str],
    ) -> RemoteRun: ...
    def close(self) -> None: ...


__all__ = ["RemoteObserver", "RemoteRun", "RemoteTarget"]
