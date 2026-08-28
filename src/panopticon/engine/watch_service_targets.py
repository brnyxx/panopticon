"""Per-target watch execution and persistence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from panopticon.badge.from_observation import persist_observation_png
from panopticon.engine.contracts import EngineDiagnostic
from panopticon.models.inventory import Transport
from panopticon.models.observation import Observation
from panopticon.store.contracts import PersistSuccess
from panopticon.store.repository import ArtifactRepository
from panopticon.util.leak_check import LeakContext

from .watch_behavior import apply_behavior_rules
from .watch_inventory import WatchTargetContext
from .watch_local_model import LocalWatchStatus
from .watch_local_production import run_local_production
from .watch_local_runtime import LocalRuntime
from .watch_model import TargetMode, WatchRequest
from .watch_observation import build_watch_observation
from .watch_remote_production import run_remote_production


def coverage_receipt(observation: Observation) -> tuple[tuple[str, str, str], ...]:
    state = observation.state
    return tuple(
        (name, stage.status.value, stage.reason_code.value)
        for name, stage in (
            ("file", state.coverage.file),
            ("net", state.coverage.net),
            ("process", state.coverage.process),
            ("dns", state.coverage.dns),
            ("proxy", state.coverage.proxy),
            ("snapshot", state.coverage.snapshot),
            ("stdio", state.coverage.stdio),
        )
    )


@dataclass(frozen=True, slots=True)
class WatchTargetReceipt:
    name: str
    status: str
    reason_code: str
    observation_path: str | None = None
    observation_count: int = 0
    evidence_count: int = 0
    finding_count: int = 0
    suppression_count: int = 0
    excluded_allowlist_count: int = 0
    findings: tuple[tuple[str, str, str, bool], ...] = ()
    coverage: tuple[tuple[str, str, str], ...] = ()


@dataclass
class TargetRun:
    receipt: WatchTargetReceipt
    observation: Observation | None = None
    failed: bool = False
    incomplete: bool = False
    unsupported: bool = False
    diagnostics: tuple[EngineDiagnostic, ...] = ()


class TargetInputs(Protocol):
    @property
    def repository(self) -> ArtifactRepository: ...

    @property
    def self_source(self) -> Path | None: ...


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
    repository: ArtifactRepository, values: Mapping[str, str]
) -> ArtifactRepository:
    secrets = tuple(value for value in values.values() if value)
    if not secrets:
        return repository
    context = LeakContext(
        home_paths=repository.context.home_paths, secrets=(*repository.context.secrets, *secrets)
    )
    return ArtifactRepository(repository.root, context)


def _finding_receipt(observation: Observation) -> tuple[tuple[str, str, str, bool], ...]:
    return tuple(
        (
            f.rule_id,
            f.severity.value if f.severity is not None else "UNKNOWN",
            f.title,
            f.suppressed_by is not None,
        )
        for f in observation.findings
    )


def _diagnostic(code: str, detail: str) -> EngineDiagnostic:
    normalized = code if code.isupper() else "WATCH_STAGE"
    return EngineDiagnostic(normalized, detail or normalized)


def _persisted_receipt(
    name: str, observation: Observation, path: str, status: str | None = None
) -> WatchTargetReceipt:
    return WatchTargetReceipt(
        name=name,
        status=status or observation.state.overall.status.value,
        reason_code="OBSERVATION_PERSISTED",
        observation_path=path,
        observation_count=1,
        evidence_count=sum(len(span.events) for span in observation.spans),
        finding_count=len(observation.findings),
        suppression_count=sum(1 for f in observation.findings if f.suppressed_by),
        excluded_allowlist_count=0,
        findings=_finding_receipt(observation),
        coverage=coverage_receipt(observation),
    )


async def run_target(
    context: WatchTargetContext,
    request: WatchRequest,
    inputs: TargetInputs,
    runtime: LocalRuntime | None,
) -> TargetRun:
    if context.target.transport is not Transport.STDIO:
        remote = await run_remote_production(context, request.options)
        if remote.observation is None:
            return TargetRun(
                WatchTargetReceipt(context.name, remote.status.value, remote.reason_code),
                unsupported=remote.status is LocalWatchStatus.UNSUPPORTED,
                incomplete=remote.status is LocalWatchStatus.INCOMPLETE,
            )
        repository = _repository_for(
            inputs.repository, {str(i): v for i, v in enumerate(remote.secrets)}
        )
        persisted = repository.persist_observation(remote.observation)
        if not isinstance(persisted, PersistSuccess):
            return TargetRun(
                WatchTargetReceipt(context.name, "FAILED", "PERSIST_FAILED"), failed=True
            )
        path = persisted.target.relative_to(repository.root).as_posix()
        if request.options.png and not isinstance(
            persist_observation_png(repository, remote.observation), PersistSuccess
        ):
            return TargetRun(
                WatchTargetReceipt(context.name, "FAILED", "PNG_PERSIST_FAILED", path), failed=True
            )
        return TargetRun(
            _persisted_receipt(context.name, remote.observation, path, remote.status.value),
            remote.observation,
        )

    raw = _raw_environment(context) if request.options.real_env else {}
    if runtime is None:
        return TargetRun(
            WatchTargetReceipt(context.name, "INCOMPLETE", "RUNTIME_UNAVAILABLE"), incomplete=True
        )
    local = await run_local_production(
        context,
        request.options,
        runtime=runtime,
        real_env=raw,
        self_source=inputs.self_source
        if request.selection.mode is TargetMode.SELF and request.options.self_read_only
        else None,
    )
    diagnostics = tuple(_diagnostic("LOCAL_DIAGNOSTIC", item) for item in local.diagnostics)
    if local.status in {LocalWatchStatus.INCOMPLETE, LocalWatchStatus.UNSUPPORTED}:
        return TargetRun(
            WatchTargetReceipt(context.name, local.status.value, local.reason_code),
            incomplete=local.status is LocalWatchStatus.INCOMPLETE,
            unsupported=local.status is LocalWatchStatus.UNSUPPORTED,
            diagnostics=diagnostics,
        )
    built = build_watch_observation(local, raw=request.options.raw)
    diagnostics = (
        *diagnostics,
        *(_diagnostic("WATCH_DIAGNOSTIC", item) for item in built.diagnostics),
    )
    behavior = apply_behavior_rules(local, built)
    if behavior is None:
        return TargetRun(
            WatchTargetReceipt(context.name, "INCOMPLETE", built.reason_code),
            incomplete=True,
            diagnostics=diagnostics,
        )
    repository = _repository_for(inputs.repository, raw)
    persisted = repository.persist_observation(behavior.observation)
    if not isinstance(persisted, PersistSuccess):
        return TargetRun(
            WatchTargetReceipt(context.name, "FAILED", "PERSIST_FAILED"),
            failed=True,
            diagnostics=diagnostics,
        )
    path = persisted.target.relative_to(repository.root).as_posix()
    if request.options.png and not isinstance(
        persist_observation_png(repository, behavior.observation), PersistSuccess
    ):
        return TargetRun(
            WatchTargetReceipt(context.name, "FAILED", "PNG_PERSIST_FAILED", path),
            failed=True,
            diagnostics=diagnostics,
        )
    return TargetRun(
        _persisted_receipt(context.name, behavior.observation, path),
        behavior.observation,
        diagnostics=diagnostics,
    )
