"""Network and span WATCH rules."""

from __future__ import annotations

from ._rules_common import (
    NETWORK_KINDS,
    absence,
    authoritative,
    declared_host,
    result,
)
from .allowlist import host_allowed
from .model import BehaviorInput, EvidenceKind, OutcomeState, WatchMatch
from .thresholds import many_urls


def rule003(context: BehaviorInput) -> WatchMatch:
    candidates = tuple(
        item
        for item in context.evidence
        if item.kind in NETWORK_KINDS and item.operation in {"connect", "request", "post", ""}
    )
    if any(not item.certain for item in candidates):
        return result(
            context,
            "WATCH-003",
            OutcomeState.UNKNOWN,
            candidates,
            reason="INCOMPLETE_EVIDENCE",
        )
    excluded = tuple(item for item in candidates if host_allowed(item.value))
    hits = tuple(
        item
        for item in candidates
        if not declared_host(context, item.value) and item not in excluded
    )
    if hits:
        state = OutcomeState.MATCH if authoritative(context) else OutcomeState.UNKNOWN
        reason = "" if state is OutcomeState.MATCH else "INCOMPLETE_DECLARATION"
        return result(context, "WATCH-003", state, hits, excluded=excluded, reason=reason)
    if candidates:
        return result(context, "WATCH-003", OutcomeState.CLEAR, candidates, excluded=excluded)
    return absence(context, "WATCH-003", EvidenceKind.NETWORK, EvidenceKind.CONNECT)


def span_rule(context: BehaviorInput, rule_id: str, span_kind: str) -> WatchMatch:
    hits = tuple(
        item
        for item in context.evidence
        if item.kind in NETWORK_KINDS
        and item.span_kind is not None
        and item.span_kind.value == span_kind
    )
    if any(not item.certain for item in hits):
        return result(
            context,
            rule_id,
            OutcomeState.UNKNOWN,
            hits,
            reason="INCOMPLETE_EVIDENCE",
        )
    if hits:
        return result(context, rule_id, OutcomeState.MATCH, hits)
    if not context.complete_spans:
        return result(context, rule_id, OutcomeState.UNKNOWN, reason="INCOMPLETE_SPANS")
    return absence(context, rule_id, EvidenceKind.NETWORK, EvidenceKind.CONNECT)


def rule004(context: BehaviorInput) -> WatchMatch:
    return span_rule(context, "WATCH-004", "idle")


def rule005(context: BehaviorInput) -> WatchMatch:
    candidates = tuple(
        item
        for item in context.evidence
        if item.kind in NETWORK_KINDS
        and item.span_kind is not None
        and item.span_kind.value == "install"
    )
    if any(not item.certain for item in candidates):
        return result(
            context,
            "WATCH-005",
            OutcomeState.UNKNOWN,
            candidates,
            reason="INCOMPLETE_EVIDENCE",
        )
    excluded = tuple(item for item in candidates if host_allowed(item.value, install=True))
    hits = tuple(item for item in candidates if item not in excluded)
    if hits:
        return result(context, "WATCH-005", OutcomeState.MATCH, hits, excluded=excluded)
    if candidates:
        return result(context, "WATCH-005", OutcomeState.CLEAR, excluded=excluded)
    return absence(context, "WATCH-005", EvidenceKind.NETWORK)


def rule007(context: BehaviorInput) -> WatchMatch:
    hits = tuple(
        item
        for item in context.evidence
        if item.kind is EvidenceKind.PROXY and item.operation.upper() == "DROP"
    )
    if any(not item.certain for item in hits):
        return result(
            context,
            "WATCH-007",
            OutcomeState.UNKNOWN,
            hits,
            reason="INCOMPLETE_EVIDENCE",
        )
    if hits:
        return result(context, "WATCH-007", OutcomeState.MATCH, hits)
    return absence(context, "WATCH-007", EvidenceKind.PROXY)


def rule012(context: BehaviorInput) -> WatchMatch:
    hits = tuple(
        item
        for item in context.evidence
        if item.kind is EvidenceKind.URL and item.value.startswith(("http://", "https://"))
    )
    if many_urls(len(hits)):
        return result(context, "WATCH-012", OutcomeState.MATCH, hits)
    return absence(
        context,
        "WATCH-012",
        EvidenceKind.URL,
        EvidenceKind.NETWORK,
        observed=hits,
    )


def rule014(context: BehaviorInput) -> WatchMatch:
    return span_rule(context, "WATCH-014", "startup")
