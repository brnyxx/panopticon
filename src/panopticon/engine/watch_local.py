"""Local runtime boundary for watch; implementations own Docker/Podman details."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from .watch_model import Evidence


@dataclass(frozen=True, slots=True)
class LocalTarget:
    name: str
    command: str
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict, repr=False)
    decoy_archive: bytes | str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "env", MappingProxyType(dict(self.env)))


@dataclass(frozen=True, slots=True)
class LocalRun:
    status: str
    reason: str
    payload: Evidence | None = field(default=None, repr=False)
    coverage: Mapping[str, str] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "coverage", MappingProxyType(dict(self.coverage)))


class LocalRuntime(Protocol):
    def available(self) -> bool: ...
    def run(
        self, target: LocalTarget, *, timeout: float, read_only: bool, env: Mapping[str, str]
    ) -> LocalRun: ...
    def cleanup(self) -> None: ...


class Decoy(Protocol):
    def manifest(self) -> Mapping[str, str]: ...
    def archive(self) -> bytes | str: ...


__all__ = ["Decoy", "LocalRun", "LocalRuntime", "LocalTarget"]
