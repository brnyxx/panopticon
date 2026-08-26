"""Container Runtime contract. See panopticon-buildplan.md §8."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ContainerSpec:
    image: str
    command: list[str]
    env: dict[str, str]
    decoy_home: Path  # copied into tmpfs $HOME; never a bind mount of the real home
    self_source: Path | None = None  # the only permitted read-only mount (`--self`)
    network: str = "pano-net"
    memory: str = "1g"
    cpus: float = 2.0
    pids_limit: int = 256
    read_only: bool = True
    cap_add: tuple[str, ...] = ("SYS_PTRACE",)
    extra_args: tuple[str, ...] = field(default_factory=tuple)


class Container(Protocol):
    id: str

    async def exec(self, argv: list[str], timeout: float) -> tuple[int, bytes, bytes]: ...

    async def logs(self) -> bytes: ...

    async def stop(self) -> None: ...

    async def rm(self) -> None: ...


class Runtime(Protocol):
    name: str

    def available(self) -> bool: ...

    async def pull(self, image_ref: str) -> None: ...

    async def run(self, spec: ContainerSpec) -> Container: ...
