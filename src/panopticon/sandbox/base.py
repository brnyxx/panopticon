"""Typed container runtime boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class SandboxError(RuntimeError):
    """A runtime boundary failure."""


@dataclass(frozen=True)
class StreamResult:
    data: bytes
    truncated: bool = False


@dataclass(frozen=True)
class ExecResult:
    returncode: int
    stdout: StreamResult
    stderr: StreamResult


@dataclass(frozen=True)
class ContainerSpec:
    image: str
    command: list[str]
    env: dict[str, str]
    decoy_home: Path  # copied into tmpfs $HOME; never a bind mount of the real home
    self_source: Path | None = None  # the only permitted read-only mount (`--self`)
    network: str = "pano-net"
    dns: str | None = None
    proxy_url: str | None = None
    memory: str = "1g"
    cpus: float = 2.0
    pids_limit: int = 256
    read_only: bool = True
    cap_add: tuple[str, ...] = ("SYS_PTRACE",)


class Container(Protocol):
    id: str

    async def exec(
        self, argv: list[str], timeout: float, stdin: bytes | None = None
    ) -> ExecResult: ...

    async def logs(self, max_bytes: int = 1_048_576) -> StreamResult: ...

    async def copy_in(self, source: Path, destination: str) -> None: ...

    async def copy_out(self, source: str, destination: Path) -> None: ...

    async def inspect(self) -> dict[str, object]: ...

    async def trace(self, max_bytes: int = 1_048_576) -> StreamResult: ...

    async def wait(self, timeout: float | None = None) -> int: ...

    async def terminate(self, timeout: float = 5.0) -> None: ...

    async def kill(self) -> None: ...

    async def stop(self) -> None: ...

    async def rm(self) -> None: ...


class Runtime(Protocol):
    name: str

    def available(self) -> bool: ...

    async def pull(self, image_ref: str) -> None: ...

    async def run(self, spec: ContainerSpec) -> Container: ...
