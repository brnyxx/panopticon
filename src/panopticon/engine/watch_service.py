"""Production watch composition from discovery through store persistence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

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
from panopticon.store.repository import ArtifactRepository

from .watch_inventory import InventoryStatus, ProductionWatchInventory
from .watch_local_runtime import LocalRuntime
from .watch_model import WatchRequest
from .watch_service_targets import TargetRun, WatchTargetReceipt, run_target


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


def _diagnostic(code: str, detail: str) -> EngineDiagnostic:
    normalized = code if code.isupper() else "WATCH_STAGE"
    return EngineDiagnostic(normalized, detail or normalized)


def _result(runs: list[TargetRun], diagnostics: tuple[EngineDiagnostic, ...]) -> Result:
    failed = any(run.failed for run in runs)
    incomplete = any(run.incomplete for run in runs)
    unsupported = any(run.unsupported for run in runs)
    observations = [run.observation for run in runs if run.observation is not None]
    all_diagnostics = (
        *diagnostics,
        *tuple(d for run in runs for d in run.diagnostics),
        *tuple(
            _diagnostic(receipt.reason_code, receipt.observation_path or receipt.name)
            for receipt in (run.receipt for run in runs)
        ),
    )
    coverage = observations[0].state.coverage if observations else None
    if failed:
        return FailedResult(diagnostics=all_diagnostics)
    if incomplete:
        return IncompleteResult(
            coverage=coverage if coverage is not None else IncompleteResult().coverage,
            diagnostics=all_diagnostics,
        )
    if unsupported and not observations:
        return UnsupportedResult(diagnostics=all_diagnostics)
    if unsupported or any(o.state.overall.status.value != "COMPLETE" for o in observations):
        return PartialResult(
            coverage=coverage if coverage is not None else PartialResult().coverage,
            diagnostics=all_diagnostics,
        )
    return CompleteResult(
        coverage=coverage if coverage is not None else CompleteResult().coverage,
        diagnostics=all_diagnostics,
    )


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
    runtime_diagnostic: EngineDiagnostic | None = None
    if runtime is None and any(c.target.transport is Transport.STDIO for c in selected.contexts):
        try:
            runtime = cast(LocalRuntime, select_runtime(request.options.runtime))
        except SandboxError:
            # Keep remote targets observable even when the local container
            # runtime is unavailable; run_target will type local targets as
            # incomplete while the remaining targets still execute.
            runtime_diagnostic = _diagnostic("RUNTIME_UNAVAILABLE", "container")
    runs: list[TargetRun] = []
    for context in selected.contexts:
        # A single malformed target must not abort an ``--all`` watch.  Keep
        # cancellation (a BaseException) visible to the caller while mapping
        # ordinary boundary failures to the same typed state as local stages.
        try:
            runs.append(await run_target(context, request, inputs, runtime))
        except (OSError, RuntimeError, TypeError, ValueError):
            runs.append(
                TargetRun(
                    WatchTargetReceipt(context.name, "INCOMPLETE", "CRASH"),
                    incomplete=True,
                    diagnostics=(_diagnostic("CRASH", context.name),),
                )
            )
    if runtime_diagnostic is not None:
        diagnostics = (*diagnostics, runtime_diagnostic)
    return WatchServiceOutcome(_result(runs, diagnostics), tuple(run.receipt for run in runs))


__all__ = ["WatchInputs", "WatchServiceOutcome", "WatchTargetReceipt", "run_watch_service"]
