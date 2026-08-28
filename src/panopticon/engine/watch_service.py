"""Production watch composition from discovery through store persistence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from panopticon.badge.from_observation import persist_observation_png
from panopticon.discovery.base import DiscoveryEnv
from panopticon.engine.contracts import (
    CompleteResult,
    EngineDiagnostic,
    FailedResult,
    IncompleteResult,
    PartialResult,
    Result,
    UnsupportedResult,
)
from panopticon.models.inventory import Transport
from panopticon.sandbox.base import SandboxError
from panopticon.sandbox.runtime import select_runtime
from panopticon.store.contracts import PersistSuccess
from panopticon.store.repository import ArtifactRepository
from panopticon.util.leak_check import LeakContext

from .watch_behavior import apply_behavior_rules
from .watch_inventory import InventoryStatus, ProductionWatchInventory, WatchTargetContext
from .watch_local_model import LocalWatchStatus
from .watch_local_production import run_local_production
from .watch_local_runtime import LocalRuntime
from .watch_model import TargetMode, WatchRequest
from .watch_observation import build_watch_observation
from .watch_remote_production import run_remote_production


@dataclass(frozen=True, slots=True)
class WatchTargetReceipt:
    name: str
    status: str
    reason_code: str
    observation_path: str | None = None


@dataclass(frozen=True, slots=True)
class WatchServiceOutcome:
    result: Result
    targets: tuple[WatchTargetReceipt, ...] = ()


@dataclass(frozen=True, slots=True)
class WatchInputs:
    env: DiscoveryEnv
    repository: ArtifactRepository
    runtime: LocalRuntime | None = None
    self_command: tuple[str, ...] | None = None
    self_source: Path | None = None


def _raw_environment(context: WatchTargetContext) -> dict[str, str]:
    value = context.raw_entry.raw.get("env")
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


def _repository_for(
    repository: ArtifactRepository,
    real_values: Mapping[str, str],
) -> ArtifactRepository:
    secrets = tuple(value for value in real_values.values() if value)
    if not secrets:
        return repository
    context = LeakContext(
        home_paths=repository.context.home_paths,
        secrets=(*repository.context.secrets, *secrets),
    )
    return ArtifactRepository(repository.root, context)


def _diagnostic(code: str, detail: str) -> EngineDiagnostic:
    normalized = code if code.isupper() else "WATCH_STAGE"
    return EngineDiagnostic(normalized, detail or normalized)


async def run_watch_service(request: WatchRequest, inputs: WatchInputs) -> WatchServiceOutcome:
    inventory = ProductionWatchInventory(inputs.env, self_command=inputs.self_command)
    selected = inventory.select(request.selection)
    diagnostics = tuple(_diagnostic("DISCOVERY", item) for item in selected.diagnostics)
    if selected.status is InventoryStatus.UNSUPPORTED:
        return WatchServiceOutcome(
            UnsupportedResult(diagnostics=(*diagnostics, _diagnostic(selected.reason_code, "self")))
        )
    if selected.status is not InventoryStatus.SELECTED:
        return WatchServiceOutcome(
            IncompleteResult(
                diagnostics=(*diagnostics, _diagnostic(selected.reason_code, "selection"))
            )
        )
    runtime = inputs.runtime
    needs_local = any(context.target.transport is Transport.STDIO for context in selected.contexts)
    if runtime is None and needs_local:
        try:
            runtime = cast(LocalRuntime, select_runtime(request.options.runtime))
        except SandboxError:
            return WatchServiceOutcome(
                UnsupportedResult(
                    diagnostics=(*diagnostics, _diagnostic("RUNTIME_UNAVAILABLE", "container"))
                )
            )
    receipts: list[WatchTargetReceipt] = []
    observations = []
    failed = incomplete = unsupported = False
    for context in selected.contexts:
        if context.target.transport is not Transport.STDIO:
            remote = await run_remote_production(context, request.options)
            if remote.observation is None:
                unsupported |= remote.status is LocalWatchStatus.UNSUPPORTED
                incomplete |= remote.status is LocalWatchStatus.INCOMPLETE
                receipts.append(
                    WatchTargetReceipt(context.name, remote.status.value, remote.reason_code)
                )
                continue
            repository = _repository_for(
                inputs.repository,
                {str(index): value for index, value in enumerate(remote.secrets)},
            )
            persisted = repository.persist_observation(remote.observation)
            if not isinstance(persisted, PersistSuccess):
                failed = True
                receipts.append(WatchTargetReceipt(context.name, "FAILED", "PERSIST_FAILED"))
                continue
            observations.append(remote.observation)
            path = persisted.target.relative_to(repository.root).as_posix()
            if request.options.png and not isinstance(
                persist_observation_png(repository, remote.observation),
                PersistSuccess,
            ):
                failed = True
                receipts.append(
                    WatchTargetReceipt(context.name, "FAILED", "PNG_PERSIST_FAILED", path)
                )
                continue
            receipts.append(
                WatchTargetReceipt(
                    context.name,
                    remote.status.value,
                    "OBSERVATION_PERSISTED",
                    path,
                )
            )
            continue
        raw_environment = _raw_environment(context) if request.options.real_env else {}
        if runtime is None:
            incomplete = True
            receipts.append(WatchTargetReceipt(context.name, "INCOMPLETE", "RUNTIME_UNAVAILABLE"))
            continue
        local = await run_local_production(
            context,
            request.options,
            runtime=runtime,
            real_env=raw_environment,
            self_source=(
                inputs.self_source
                if request.selection.mode is TargetMode.SELF and request.options.self_read_only
                else None
            ),
        )
        if local.status in {LocalWatchStatus.INCOMPLETE, LocalWatchStatus.UNSUPPORTED}:
            incomplete |= local.status is LocalWatchStatus.INCOMPLETE
            unsupported |= local.status is LocalWatchStatus.UNSUPPORTED
            receipts.append(WatchTargetReceipt(context.name, local.status.value, local.reason_code))
            continue
        built = build_watch_observation(local)
        behavior = apply_behavior_rules(local, built)
        if behavior is None:
            incomplete = True
            receipts.append(WatchTargetReceipt(context.name, "INCOMPLETE", built.reason_code))
            continue
        repository = _repository_for(inputs.repository, raw_environment)
        persisted = repository.persist_observation(behavior.observation)
        if not isinstance(persisted, PersistSuccess):
            failed = True
            receipts.append(WatchTargetReceipt(context.name, "FAILED", "PERSIST_FAILED"))
            continue
        observations.append(behavior.observation)
        path = persisted.target.relative_to(repository.root).as_posix()
        if request.options.png:
            card = persist_observation_png(repository, behavior.observation)
            if not isinstance(card, PersistSuccess):
                failed = True
                receipts.append(
                    WatchTargetReceipt(
                        context.name,
                        "FAILED",
                        "PNG_PERSIST_FAILED",
                        path,
                    )
                )
                continue
        receipts.append(
            WatchTargetReceipt(
                context.name,
                behavior.observation.state.overall.status.value,
                "OBSERVATION_PERSISTED",
                path,
            )
        )
    receipt_diagnostics = tuple(
        _diagnostic(receipt.reason_code, receipt.observation_path or receipt.name)
        for receipt in receipts
    )
    all_diagnostics = (*diagnostics, *receipt_diagnostics)
    coverage = observations[0].state.coverage if observations else None
    if failed:
        result: Result = FailedResult(diagnostics=all_diagnostics)
    elif incomplete:
        result = IncompleteResult(
            coverage=coverage if coverage is not None else IncompleteResult().coverage,
            diagnostics=all_diagnostics,
        )
    elif unsupported and not observations:
        result = UnsupportedResult(diagnostics=all_diagnostics)
    elif unsupported or any(
        observation.state.overall.status.value != "COMPLETE" for observation in observations
    ):
        result = PartialResult(
            coverage=coverage if coverage is not None else PartialResult().coverage,
            diagnostics=all_diagnostics,
        )
    else:
        result = CompleteResult(
            coverage=coverage if coverage is not None else CompleteResult().coverage,
            diagnostics=all_diagnostics,
        )
    return WatchServiceOutcome(result, tuple(receipts))


__all__ = ["WatchInputs", "WatchServiceOutcome", "WatchTargetReceipt", "run_watch_service"]
