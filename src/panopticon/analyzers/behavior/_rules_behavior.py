"""File, process, leak, declaration, and hint WATCH rules."""

from __future__ import annotations

from ._rules_common import (
    FILE_KINDS,
    NETWORK_KINDS,
    absence,
    authoritative,
    authorities,
    covered,
    declared_host,
    declared_path,
    result,
)
from .model import BehaviorInput, EvidenceKind, OutcomeState, WatchMatch
from .thresholds import broad_enumeration_count

_CONFIG_NAMES = (".gitconfig", ".bashrc", ".zshrc", ".profile", ".config/")
_TOOLING = frozenset(
    {"python", "python3", "node", "ruby", "perl", "sh", "bash", "zsh", "git", "npm", "npx", "uv"}
)


def rule001(context: BehaviorInput) -> WatchMatch:
    observable = {
        EvidenceKind.LEAK,
        EvidenceKind.NETWORK,
        EvidenceKind.WRITE,
        EvidenceKind.PROCESS,
        EvidenceKind.STDERR,
    }
    hits = tuple(
        item
        for item in context.evidence
        if item.certain
        and item.kind in observable
        and (item.kind is EvidenceKind.LEAK or item.value in context.decoys)
    )
    if hits:
        return result(context, "WATCH-001", OutcomeState.MATCH, hits)
    uncertain = tuple(
        item for item in context.evidence if not item.certain and item.kind in observable
    )
    return absence(context, "WATCH-001", EvidenceKind.LEAK, observed=uncertain)


def rule002(context: BehaviorInput) -> WatchMatch:
    candidates = tuple(
        item
        for item in context.evidence
        if item.kind in {EvidenceKind.FILE, EvidenceKind.READ}
        and item.operation in {"read", "open", ""}
    )
    if any(not item.certain for item in candidates):
        return result(
            context,
            "WATCH-002",
            OutcomeState.UNKNOWN,
            candidates,
            reason="INCOMPLETE_EVIDENCE",
        )
    hits = tuple(
        item
        for item in candidates
        if item.value in context.decoys and not declared_path(context, item.value)
    )
    if hits:
        state = OutcomeState.MATCH if authoritative(context) else OutcomeState.UNKNOWN
        reason = "" if state is OutcomeState.MATCH else "INCOMPLETE_DECLARATION"
        return result(context, "WATCH-002", state, hits, reason=reason)
    return absence(context, "WATCH-002", EvidenceKind.FILE, EvidenceKind.READ)


def rule006(context: BehaviorInput) -> WatchMatch:
    candidates = tuple(
        item
        for item in context.evidence
        if item.kind in {EvidenceKind.FILE, EvidenceKind.READ}
        and any(name in item.value for name in _CONFIG_NAMES)
    )
    if any(not item.certain for item in candidates):
        return result(
            context,
            "WATCH-006",
            OutcomeState.UNKNOWN,
            candidates,
            reason="INCOMPLETE_EVIDENCE",
        )
    hits = tuple(item for item in candidates if not declared_path(context, item.value))
    if hits:
        state = OutcomeState.MATCH if authoritative(context) else OutcomeState.UNKNOWN
        reason = "" if state is OutcomeState.MATCH else "INCOMPLETE_DECLARATION"
        return result(context, "WATCH-006", state, hits, reason=reason)
    return absence(context, "WATCH-006", EvidenceKind.FILE, EvidenceKind.READ)


def rule008(context: BehaviorInput) -> WatchMatch:
    candidates = tuple(item for item in context.evidence if item.kind is EvidenceKind.PROCESS)
    excluded = tuple(
        item
        for item in candidates
        if item.value.rsplit("/", 1)[-1].split(" ", 1)[0].casefold() in _TOOLING
    )
    hits = tuple(
        item
        for item in candidates
        if item not in excluded
        and not any(
            item.value == process
            for authority in authorities(context)
            for process in authority.processes
        )
    )
    if hits:
        state = OutcomeState.MATCH if authoritative(context) else OutcomeState.UNKNOWN
        reason = "" if state is OutcomeState.MATCH else "INCOMPLETE_DECLARATION"
        return result(context, "WATCH-008", state, hits, excluded=excluded, reason=reason)
    if candidates:
        return result(context, "WATCH-008", OutcomeState.CLEAR, excluded=excluded)
    return absence(context, "WATCH-008", EvidenceKind.PROCESS)


def rule009(context: BehaviorInput) -> WatchMatch:
    evidence = tuple(
        item
        for item in context.evidence
        if item.kind in {EvidenceKind.FILE, EvidenceKind.STAT, EvidenceKind.READ}
    )
    if broad_enumeration_count(tuple(item.value for item in evidence)) >= 10:
        return result(context, "WATCH-009", OutcomeState.MATCH, evidence)
    return absence(
        context,
        "WATCH-009",
        EvidenceKind.FILE,
        EvidenceKind.STAT,
        observed=evidence,
    )


def rule010(context: BehaviorInput) -> WatchMatch:
    if not authoritative(context):
        return result(
            context,
            "WATCH-010",
            OutcomeState.UNKNOWN,
            context.evidence,
            reason="INCOMPLETE_DECLARATION",
        )
    required = (EvidenceKind.FILE, EvidenceKind.NETWORK, EvidenceKind.PROCESS)
    if not all(covered(context, kind) for kind in required) or not context.complete_spans:
        return result(context, "WATCH-010", OutcomeState.UNKNOWN, reason="INCOMPLETE_COVERAGE")
    if context.suppressed_rule_ids or any(not item.certain for item in context.evidence):
        return result(
            context,
            "WATCH-010",
            OutcomeState.UNKNOWN,
            reason="HIDDEN_OR_INCOMPLETE_EVIDENCE",
        )
    excluded_processes = tuple(
        item
        for item in context.evidence
        if item.kind is EvidenceKind.PROCESS
        and item.value.rsplit("/", 1)[-1].split(" ", 1)[0].casefold() in _TOOLING
    )
    if excluded_processes:
        return result(
            context,
            "WATCH-010",
            OutcomeState.UNKNOWN,
            excluded_processes,
            reason="EXCLUDED_EVIDENCE",
        )
    unmatched = tuple(
        item
        for item in context.evidence
        if (item.kind in FILE_KINDS and not declared_path(context, item.value))
        or (item.kind in NETWORK_KINDS and not declared_host(context, item.value))
        or (
            item.kind is EvidenceKind.PROCESS
            and not any(item.value in authority.processes for authority in authorities(context))
        )
        or item.kind in {EvidenceKind.LEAK, EvidenceKind.PROXY}
    )
    state = OutcomeState.CLEAR if unmatched else OutcomeState.MATCH
    return result(context, "WATCH-010", state, unmatched)


def rule011(context: BehaviorInput) -> WatchMatch:
    withheld = context.withheld or not authoritative(context)
    return result(
        context,
        "WATCH-011",
        OutcomeState.MATCH if withheld else OutcomeState.CLEAR,
        reason="DECLARATION_INCOMPLETE" if withheld else "",
    )


def rule013(context: BehaviorInput) -> WatchMatch:
    if not any(authority.read_only_hint is True for authority in authorities(context)):
        return result(context, "WATCH-013", OutcomeState.CLEAR)
    uncertain = tuple(
        item for item in context.evidence if item.kind in NETWORK_KINDS and item.tls and item.post
    )
    if uncertain:
        return result(
            context, "WATCH-013", OutcomeState.UNKNOWN, uncertain, reason="OPAQUE_TLS_BODY"
        )
    hits = tuple(
        item
        for item in context.evidence
        if item.kind is EvidenceKind.WRITE or (item.kind in NETWORK_KINDS and item.post)
    )
    if hits:
        return result(context, "WATCH-013", OutcomeState.MATCH, hits)
    return absence(context, "WATCH-013", EvidenceKind.WRITE, EvidenceKind.NETWORK)
