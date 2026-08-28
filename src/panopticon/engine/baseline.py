"""Typed baseline create/list/show/remove engine pipeline."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from panopticon.baseline.service import BaselineService
from panopticon.discovery import combine_results, discover, registered_adapters
from panopticon.discovery.base import DiscoveryEnv, DiscoveryStatus
from panopticon.engine.contracts import (
    CompleteResult,
    EngineDiagnostic,
    EngineReason,
    FailedResult,
    Result,
)
from panopticon.inventory.normalize import normalize_entries
from panopticon.models.artifacts import Baseline
from panopticon.models.inventory import InstalledServer
from panopticon.store.repository import ArtifactRepository, LoadStatus, RemoveStatus


@dataclass(frozen=True, slots=True)
class BaselineRequest:
    action: str
    identifier: str | None = None
    label: str | None = None


@dataclass(frozen=True, slots=True)
class BaselineOutcome:
    result: Result
    baselines: tuple[Baseline, ...] = ()
    removed: RemoveStatus | None = None


def runtime_environment() -> DiscoveryEnv:
    platform = "darwin" if sys.platform == "darwin" else "windows" if os.name == "nt" else "linux"
    return DiscoveryEnv(Path.home(), Path.cwd(), platform, dict(os.environ))


def collect_inventory(
    env: DiscoveryEnv,
) -> tuple[tuple[InstalledServer, ...], tuple[EngineDiagnostic, ...]]:
    servers: list[InstalledServer] = []
    diagnostics: list[EngineDiagnostic] = []
    for adapter in registered_adapters(env):
        parsed = combine_results(discover(adapter, env))
        if parsed.status is DiscoveryStatus.FOUND:
            servers.extend(
                normalize_entries(parsed.entries, client=adapter.name, home=str(env.home))
            )
        elif parsed.status not in {DiscoveryStatus.NOT_FOUND}:
            diagnostics.append(EngineDiagnostic("DISCOVERY_FAILED", adapter.name))
    return (
        tuple(sorted(servers, key=lambda item: str(item.installation_id))),
        tuple(diagnostics),
    )


def run_baseline(
    request: BaselineRequest,
    *,
    repository: ArtifactRepository | None = None,
    env: DiscoveryEnv | None = None,
    now: datetime | None = None,
) -> BaselineOutcome:
    service = BaselineService(repository or ArtifactRepository())
    if request.action == "create":
        inventory, diagnostics = collect_inventory(env or runtime_environment())
        loaded = service.create(inventory, now=now or datetime.now(UTC), label=request.label)
        if loaded.baseline is None:
            return BaselineOutcome(
                FailedResult(
                    reason_code=EngineReason.STAGE_ERROR,
                    diagnostics=(EngineDiagnostic(loaded.reason_code, "baseline"),),
                )
            )
        return BaselineOutcome(CompleteResult(diagnostics=diagnostics), (loaded.baseline,))
    if request.action == "list":
        loads = service.list()
        baselines = tuple(item.baseline for item in loads if item.baseline is not None)
        diagnostics = tuple(
            EngineDiagnostic(item.reason_code, "baseline")
            for item in loads
            if item.status is not LoadStatus.AVAILABLE
        )
        result: Result = (
            CompleteResult(diagnostics=diagnostics)
            if not diagnostics
            else FailedResult(reason_code=EngineReason.STAGE_ERROR, diagnostics=diagnostics)
        )
        return BaselineOutcome(result, baselines)
    if request.action == "show" and request.identifier:
        loaded = service.show(request.identifier)
        if loaded.baseline is not None:
            return BaselineOutcome(CompleteResult(), (loaded.baseline,))
        return BaselineOutcome(
            FailedResult(
                reason_code=EngineReason.STAGE_ERROR,
                diagnostics=(EngineDiagnostic(loaded.reason_code, request.identifier),),
            )
        )
    if request.action == "rm" and request.identifier:
        removed = service.remove(request.identifier)
        result = (
            CompleteResult()
            if removed is RemoveStatus.REMOVED
            else FailedResult(
                reason_code=EngineReason.STAGE_ERROR,
                diagnostics=(EngineDiagnostic(f"BASELINE_{removed.value}", request.identifier),),
            )
        )
        return BaselineOutcome(result, removed=removed)
    return BaselineOutcome(
        FailedResult(
            reason_code=EngineReason.STAGE_ERROR,
            diagnostics=(EngineDiagnostic("BASELINE_USAGE", request.action),),
        )
    )


__all__ = [
    "BaselineOutcome",
    "BaselineRequest",
    "collect_inventory",
    "run_baseline",
    "runtime_environment",
]
