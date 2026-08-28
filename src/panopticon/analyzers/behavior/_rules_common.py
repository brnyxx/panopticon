"""Shared deterministic helpers for WATCH rule families."""

from __future__ import annotations

from .model import (
    Authority,
    BehaviorInput,
    CoverageState,
    DeclaredAuthority,
    EvidenceKind,
    OutcomeState,
    WatchEvidence,
    WatchMatch,
)

NETWORK_KINDS = frozenset(
    {EvidenceKind.NETWORK, EvidenceKind.DNS, EvidenceKind.CONNECT, EvidenceKind.REQUEST}
)
FILE_KINDS = frozenset(
    {EvidenceKind.FILE, EvidenceKind.STAT, EvidenceKind.READ, EvidenceKind.WRITE}
)


def result(
    context: BehaviorInput,
    rule_id: str,
    state: OutcomeState,
    evidence: tuple[WatchEvidence, ...] = (),
    *,
    excluded: tuple[WatchEvidence, ...] = (),
    reason: str = "",
) -> WatchMatch:
    def order(item: WatchEvidence) -> tuple[str, str, str, str]:
        return (item.span_id or "", item.kind.value, item.value, item.operation)

    return WatchMatch(
        rule_id=rule_id,
        state=state,
        evidence=tuple(sorted(evidence, key=order)),
        excluded=tuple(sorted(excluded, key=order)),
        reason=reason,
        suppressed=rule_id in context.suppressed_rule_ids,
    )


def authorities(context: BehaviorInput) -> tuple[Authority, ...]:
    selected = (
        context.authorities
        if context.current_tool is None
        else tuple(item for item in context.authorities if item.tool == context.current_tool)
    )
    return tuple(sorted(selected, key=lambda item: item.tool))


def covered(context: BehaviorInput, *kinds: EvidenceKind) -> bool:
    return any(context.coverage.get(kind) is CoverageState.COMPLETE for kind in kinds)


def absence(
    context: BehaviorInput,
    rule_id: str,
    *kinds: EvidenceKind,
    observed: tuple[WatchEvidence, ...] = (),
) -> WatchMatch:
    if covered(context, *kinds):
        return result(context, rule_id, OutcomeState.CLEAR)
    return result(
        context,
        rule_id,
        OutcomeState.UNKNOWN,
        observed,
        reason="INCOMPLETE_COVERAGE",
    )


def declared_path(context: BehaviorInput, value: str) -> bool:
    return any(
        value == path or value.startswith(path.rstrip("/") + "/")
        for authority in authorities(context)
        for path in authority.paths
    )


def declared_host(context: BehaviorInput, value: str) -> bool:
    normalized = value.lower().rstrip(".")
    return any(
        normalized == host.lower().rstrip(".")
        for authority in authorities(context)
        for host in authority.hosts
    )


def authoritative(context: BehaviorInput) -> bool:
    declared = authorities(context)
    return bool(declared) and all(
        item.authority is DeclaredAuthority.AUTHORITATIVE
        and item.coverage is CoverageState.COMPLETE
        for item in declared
    )
