"""Local runtime boundary for watch; implementations own Docker/Podman details."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LocalTarget:
    name: str
    command: str
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LocalRun:
    status: str
    reason: str
    payload: object | None = None
    coverage: Mapping[str, str] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()


class LocalRuntime(Protocol):
    def available(self) -> bool: ...
    def run(
        self, target: LocalTarget, *, timeout: float, read_only: bool, env: Mapping[str, str]
    ) -> LocalRun: ...
    def cleanup(self) -> None: ...


class Decoy(Protocol):
    def manifest(self) -> object: ...
    def archive(self) -> object: ...


__all__ = ["Decoy", "LocalRun", "LocalRuntime", "LocalTarget"]
