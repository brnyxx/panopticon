"""Pure orchestration of watch stages over injected boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from .watch_local import Decoy, LocalRuntime, LocalTarget
from .watch_model import (
    Coverage,
    Evidence,
    Inventory,
    PersistenceCandidate,
    WatchOutcome,
    WatchRequest,
    WatchTarget,
)
from .watch_remote import RemoteObserver, RemoteTarget


class RuleExecutor(Protocol):
    def evaluate(
        self, evidence: Evidence, *, target: WatchTarget
    ) -> tuple[PersistenceCandidate, ...]: ...


class McpDriver(Protocol):
    def drive(
        self, evidence: Evidence, *, calls: int, args: tuple[str, ...], timeout: float, idle: float
    ) -> Evidence: ...


class SpanCollector(Protocol):
    def collect(self, evidence: Evidence) -> PersistenceCandidate: ...


class EventCollector(Protocol):
    def collect(self, evidence: Evidence) -> PersistenceCandidate: ...


class DeclaredExtractor(Protocol):
    def extract(self, evidence: Evidence) -> PersistenceCandidate: ...


class Authority(Protocol):
    def apply(
        self, declared: PersistenceCandidate, *, target: WatchTarget
    ) -> PersistenceCandidate: ...


class Cancellation(Protocol):
    def cancelled(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class WatchDependencies:
    inventory: Inventory
    local: LocalRuntime | None = None
    remote: RemoteObserver | None = None
    decoy: Decoy | None = None
    declared: DeclaredExtractor | None = None
    authority: Authority | None = None
    rules: RuleExecutor | None = None
    mcp: McpDriver | None = None
    spans: SpanCollector | None = None
    events: EventCollector | None = None
    cancellation: Cancellation | None = None
    environment: Mapping[str, str] = field(default_factory=dict, repr=False)
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))


def _coverage(values: Mapping[str, str], remote: bool) -> dict[str, Coverage]:
    sources = ("file", "net", "process", "dns", "proxy", "snapshot", "stdio")
    result: dict[str, Coverage] = dict.fromkeys(sources, Coverage.UNKNOWN)
    for key, value in values.items():
        try:
            result[key] = Coverage(value)
        except ValueError:
            result[key] = Coverage.UNKNOWN
    if remote:
        result["file"] = Coverage.UNSUPPORTED
        result["process"] = Coverage.UNSUPPORTED
    return result


class WatchStages:
    def __init__(self, dependencies: WatchDependencies) -> None:
        self._d = dependencies

    def run(self, request: WatchRequest) -> tuple[WatchOutcome, ...]:
        targets = self._d.inventory.select(request.selection)
        outcomes: list[WatchOutcome] = []
        for target in targets:
            if self._d.cancellation is not None and self._d.cancellation.cancelled():
                outcomes.append(WatchOutcome(target.name, "INCOMPLETE", "CANCELLED"))
                break
            outcomes.append(self._run_target(target, request))
        return tuple(outcomes)

    def _run_target(self, target: WatchTarget, request: WatchRequest) -> WatchOutcome:
        name = target.name
        used_local = False
        used_remote = False
        try:
            if (
                target.destructive
                and (request.options.real_env or bool(request.options.headers))
                and not request.options.allow_destructive
            ):
                return WatchOutcome(name, "SKIPPED", "SKIPPED_DESTRUCTIVE")
            transport = str(target.transport)
            if transport == "stdio":
                if self._d.local is None:
                    return WatchOutcome(name, "UNSUPPORTED", "RUNTIME_UNAVAILABLE")
                if not self._d.local.available():
                    return WatchOutcome(name, "UNSUPPORTED", "RUNTIME_UNAVAILABLE")
                used_local = True
                command = target.command
                if not isinstance(command, str):
                    return WatchOutcome(name, "UNSUPPORTED", "UNINSTRUMENTABLE_LOCAL_TARGET")
                env = dict(self._d.environment) if request.options.real_env else {}
                decoy_archive: bytes | str | None = None
                if self._d.decoy is not None:
                    env = {**self._d.decoy.manifest(), **env}
                    decoy_archive = self._d.decoy.archive()
                local_run = self._d.local.run(
                    LocalTarget(name, command, target.args, env, decoy_archive),
                    timeout=request.options.timeout,
                    read_only=request.options.self_read_only,
                    env=env,
                )
                payload = local_run.payload
                status = local_run.status
                reason = local_run.reason
                coverage = local_run.coverage
                diagnostics = local_run.diagnostics
                remote_target = False
            else:
                if self._d.remote is None:
                    return WatchOutcome(name, "UNSUPPORTED", "UNSUPPORTED_TRANSPORT")
                used_remote = True
                endpoint = target.url or ""
                headers = dict(self._d.headers)
                if self._d.decoy is not None:
                    manifest = self._d.decoy.manifest()
                    headers.update(
                        {key: value for key, value in manifest.items() if key in headers}
                    )
                for header in request.options.headers:
                    headers.setdefault(header, "")
                remote_run = self._d.remote.observe(
                    RemoteTarget(name, endpoint, headers),
                    calls=request.options.calls,
                    timeout=request.options.timeout,
                    idle=request.options.idle,
                    headers=headers,
                )
                payload = remote_run.payload
                status = remote_run.status
                reason = remote_run.reason
                coverage = remote_run.coverage
                diagnostics = remote_run.diagnostics
                remote_target = True
            findings: tuple[PersistenceCandidate, ...] = ()
            persistence: list[PersistenceCandidate] = []
            evidence = payload
            if self._d.mcp is not None and evidence is not None:
                evidence = self._d.mcp.drive(
                    evidence,
                    calls=request.options.calls,
                    args=request.options.args,
                    timeout=request.options.timeout,
                    idle=request.options.idle,
                )
            if self._d.spans is not None and evidence is not None:
                persistence.append(self._d.spans.collect(evidence))
            if self._d.events is not None and evidence is not None:
                persistence.append(self._d.events.collect(evidence))
            if self._d.declared is not None and evidence is not None:
                declared = self._d.declared.extract(evidence)
                if self._d.authority is not None:
                    declared = self._d.authority.apply(declared, target=target)
                persistence.append(declared)
            if self._d.rules is not None and evidence is not None:
                findings = self._d.rules.evaluate(evidence, target=target)
            return WatchOutcome(
                name,
                status,
                reason,
                _coverage(coverage, remote_target),
                diagnostics,
                findings,
                tuple(persistence),
            )
        except TimeoutError:
            return WatchOutcome(name, "INCOMPLETE", "TIMEOUT")
        except (OSError, RuntimeError, TypeError, ValueError):
            return WatchOutcome(name, "INCOMPLETE", "CRASH")
        finally:
            if used_local and self._d.local is not None:
                self._d.local.cleanup()
            if used_remote and self._d.remote is not None:
                self._d.remote.close()


__all__ = [
    "Authority",
    "Cancellation",
    "DeclaredExtractor",
    "EventCollector",
    "McpDriver",
    "RuleExecutor",
    "SpanCollector",
    "WatchDependencies",
    "WatchStages",
]
