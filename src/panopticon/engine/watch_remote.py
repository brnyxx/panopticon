"""Remote observer boundary. Remote file/process evidence is never inferred."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RemoteTarget:
    name: str
    endpoint: str
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RemoteRun:
    status: str
    reason: str
    payload: object | None = None
    coverage: Mapping[str, str] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()


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
