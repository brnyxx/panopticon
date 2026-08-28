"""Convert persisted observation evidence and execute registered WATCH rules."""

from __future__ import annotations

from dataclasses import dataclass

from panopticon.analyzers.behavior.model import Authority as BehaviorAuthority
from panopticon.analyzers.behavior.model import (
    BehaviorInput,
    CoverageState,
    DeclaredAuthority,
    EvidenceKind,
    WatchEvidence,
)
from panopticon.analyzers.behavior.registry_rules import register_rules
from panopticon.declared.model import Authority, DeclaredScope, ScopeGrant
from panopticon.models.finding import Finding
from panopticon.models.observation import Observation
from panopticon.models.state import StageStatus
from panopticon.rules.context import RuleContext, SourceState
from panopticon.rules.registry import run_rules

from .watch_local_model import LocalWatchResult
from .watch_observation import WatchObservationBuild


@dataclass(frozen=True, slots=True)
class BehaviorBuild:
    observation: Observation
    diagnostics: tuple[str, ...] = ()


def _coverage(status: StageStatus) -> CoverageState:
    if status is StageStatus.COMPLETE:
        return CoverageState.COMPLETE
    if status is StageStatus.UNSUPPORTED:
        return CoverageState.UNSUPPORTED
    if status is StageStatus.NOT_REQUESTED:
        return CoverageState.NONE
    return CoverageState.PARTIAL


def _authority(tool: str, grant: ScopeGrant, read_only: bool | None) -> BehaviorAuthority:
    if grant.authority is Authority.AUTHORITATIVE and grant.complete:
        coverage = CoverageState.COMPLETE
        authority = DeclaredAuthority.AUTHORITATIVE
    elif any((grant.paths, grant.hosts, grant.processes, grant.capabilities)):
        coverage = CoverageState.PARTIAL
        authority = DeclaredAuthority.PARTIAL
    else:
        coverage = CoverageState.NONE
        authority = DeclaredAuthority.NONE
    return BehaviorAuthority(
        tool=tool,
        paths=grant.paths,
        hosts=grant.hosts,
        processes=grant.processes,
        read_only_hint=read_only,
        coverage=coverage,
        authority=authority,
    )


def _authorities(result: LocalWatchResult, scope: DeclaredScope) -> tuple[BehaviorAuthority, ...]:
    hints = {tool.name: tool.read_only for tool in result.tools}
    return tuple(
        _authority(tool, grant, hints.get(tool)) for tool, grant in sorted(scope.tools.items())
    )


def _evidence(result: LocalWatchResult, observation: Observation) -> tuple[WatchEvidence, ...]:
    kinds = {span.span_id: span.kind for span in result.spans}
    output: list[WatchEvidence] = []
    for span in observation.spans:
        span_kind = kinds.get(str(span.span_id))
        for event in span.events:
            value = event.root
            if value.kind == "file":
                kind = {
                    "read": EvidenceKind.READ,
                    "stat": EvidenceKind.STAT,
                    "write": EvidenceKind.WRITE,
                    "create": EvidenceKind.WRITE,
                    "delete": EvidenceKind.WRITE,
                    "exec": EvidenceKind.FILE,
                }[value.op]
                output.append(
                    WatchEvidence(
                        kind,
                        str(value.path),
                        value.op,
                        str(span.span_id),
                        span_kind,
                    )
                )
            elif value.kind == "net":
                output.append(
                    WatchEvidence(
                        EvidenceKind.CONNECT,
                        str(value.host),
                        value.op,
                        str(span.span_id),
                        span_kind,
                        source=value.via,
                        tls=value.port == 443,
                    )
                )
            elif value.kind == "proc":
                output.append(
                    WatchEvidence(
                        EvidenceKind.PROCESS,
                        value.argv[0],
                        value.op,
                        str(span.span_id),
                        span_kind,
                    )
                )
            elif value.kind == "leak":
                output.append(
                    WatchEvidence(
                        EvidenceKind.LEAK,
                        value.decoy_key,
                        value.sink,
                        str(span.span_id),
                        span_kind,
                    )
                )
    return tuple(output)


def _coverage_map(observation: Observation) -> dict[EvidenceKind, CoverageState]:
    values = observation.state.coverage
    return {
        EvidenceKind.FILE: _coverage(values.file.status),
        EvidenceKind.READ: _coverage(values.file.status),
        EvidenceKind.STAT: _coverage(values.file.status),
        EvidenceKind.WRITE: _coverage(values.file.status),
        EvidenceKind.NETWORK: _coverage(values.net.status),
        EvidenceKind.CONNECT: _coverage(values.net.status),
        EvidenceKind.PROCESS: _coverage(values.process.status),
        EvidenceKind.DNS: _coverage(values.dns.status),
        EvidenceKind.PROXY: _coverage(values.proxy.status),
        EvidenceKind.LEAK: _coverage(values.stdio.status),
    }


def apply_behavior_rules(
    result: LocalWatchResult,
    build: WatchObservationBuild,
) -> BehaviorBuild | None:
    observation = build.observation
    scope = build.declared_scope
    if observation is None or scope is None:
        return None
    register_rules()
    all_evidence = _evidence(result, observation)
    authorities = _authorities(result, scope)
    call_tools = tuple(tool.name for tool in result.tools)
    reserved = {span.span_id for span in result.spans if span.kind.value != "call"}
    decoys = frozenset(
        {
            event.value
            for event in all_evidence
            if event.kind is EvidenceKind.LEAK
            or (event.kind in {EvidenceKind.FILE, EvidenceKind.READ} and "~" in event.value)
        }
    )
    findings: dict[str, Finding] = {}
    prior_suppressed = {
        finding.rule_id: finding.suppressed_by
        for finding in observation.findings
        if finding.suppressed_by is not None
    }
    diagnostics: list[str] = []
    for tool in call_tools or (None,):
        span_ids = {
            span.span_id for span in result.spans if tool is None or span.tool == tool
        } | reserved
        evidence = tuple(item for item in all_evidence if item.span_id in span_ids)
        behavior = BehaviorInput(
            evidence=evidence,
            authorities=authorities,
            decoys=decoys,
            coverage=_coverage_map(observation),
            complete_spans=build.uncovered_events == 0,
            withheld=observation.declared.completeness.value != "COMPLETE",
            suppressed_rule_ids=frozenset(prior_suppressed),
            current_tool=tool,
            server_id=result.context.target.server_id,
            installation_id=result.context.target.installation_id,
            observation_id=observation.observation_id,
            observed_at=observation.observed_at,
        )
        produced, rule_diagnostics = run_rules(
            RuleContext(observation=SourceState.available(behavior)),
            at=observation.observed_at,
            line="observe",
            server_id=str(observation.server_id),
        )
        for finding in produced:
            # Re-analysis must not silently clear an existing suppression reason.
            reason = prior_suppressed.get(finding.rule_id)
            if reason is not None and finding.suppressed_by != reason:
                finding = finding.model_copy(update={"suppressed_by": reason})
            findings[str(finding.id)] = finding
        diagnostics.extend(
            f"{diagnostic.rule_id}:{diagnostic.code}" for diagnostic in rule_diagnostics
        )
    # A suppressed finding is durable state. Keep it when a subsequent
    # evaluation withholds a verdict (for example WATCH-010 under suppression)
    # rather than silently deleting the user's suppression record.
    for prior in observation.findings:
        if prior.suppressed_by is not None and str(prior.id) not in findings:
            findings[str(prior.id)] = prior
    updated = observation.model_copy(
        update={"findings": tuple(findings[key] for key in sorted(findings))}
    )
    return BehaviorBuild(updated, tuple(sorted(set(diagnostics))))


__all__ = ["BehaviorBuild", "apply_behavior_rules"]
