"""Dependency-injected watch service; no persistence or presentation side effects."""

from __future__ import annotations

from typing import Protocol

from .watch_model import TargetMode, TargetSelection, WatchOptions, WatchOutcome, WatchRequest
from .watch_stages import WatchDependencies, WatchStages


class WatchPlan(Protocol):
    def run(self, request: WatchRequest) -> tuple[WatchOutcome, ...]: ...


class WatchService:
    """Compose inventory, runtime/observer and analysis seams into value outcomes."""

    def __init__(self, dependencies: WatchDependencies) -> None:
        self._stages = WatchStages(dependencies)

    def run(self, request: WatchRequest) -> tuple[WatchOutcome, ...]:
        return self._stages.run(request)

    def watch(
        self,
        *,
        name: str | None = None,
        all_targets: bool = False,
        self_target: bool = False,
        calls: int = 1,
        args: tuple[str, ...] = (),
        timeout: float = 20.0,
        idle: float = 0.0,
        real_env: tuple[str, ...] = (),
        real_env_all: bool = False,
        headers: tuple[str, ...] = (),
        allow_destructive: bool = False,
        self_read_only: bool = False,
    ) -> tuple[WatchOutcome, ...]:
        selected = sum((name is not None, all_targets, self_target))
        if selected != 1:
            raise ValueError("select exactly one of name, all_targets, self_target")
        mode = (
            TargetMode.NAME
            if name is not None
            else TargetMode.ALL
            if all_targets
            else TargetMode.SELF
        )
        request = WatchRequest(
            TargetSelection(mode, name),
            WatchOptions(
                calls=calls,
                timeout=timeout,
                idle=idle,
                args=args,
                real_env=real_env,
                real_env_all=real_env_all,
                headers=headers,
                allow_destructive=allow_destructive,
                self_read_only=self_read_only,
            ),
        )
        return self.run(request)


__all__ = [
    "TargetMode",
    "TargetSelection",
    "WatchOptions",
    "WatchOutcome",
    "WatchPlan",
    "WatchRequest",
    "WatchService",
]
