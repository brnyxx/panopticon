"""Executable deterministic WATCH rule evaluation."""

from __future__ import annotations

from collections.abc import Callable

from .allowlist import host_allowed
from .catalog import RULE_CATALOG
from .model import Authority, BehaviorInput, CoverageState, OutcomeState, WatchEvidence, WatchMatch
from .thresholds import broad_enumeration_count, many_urls

_CONFIG_NAMES = (".gitconfig", ".bashrc", ".zshrc", ".profile", ".config/")
_TOOLING = (
    "python",
    "python3",
    "node",
    "ruby",
    "perl",
    "sh",
    "bash",
    "zsh",
    "git",
    "npm",
    "npx",
    "uv",
)
_NETWORK = {"network", "dns", "connect", "request", "post"}


def _result(
    rule_id: str, state: OutcomeState, evidence: tuple[WatchEvidence, ...] = (), reason: str = ""
) -> WatchMatch:
    return WatchMatch(
        rule_id,
        state,
        tuple(sorted(evidence, key=lambda e: (e.span_id or "", e.kind, e.value, e.operation))),
        reason,
    )


def _authorities(ctx: BehaviorInput) -> tuple[Authority, ...]:
    return tuple(sorted(ctx.authorities, key=lambda a: a.tool))


def _declared_path(ctx: BehaviorInput, value: str) -> bool:
    return any(
        value == p or value.startswith(p.rstrip("/") + "/")
        for a in _authorities(ctx)
        for p in a.paths
    )


def _declared_host(ctx: BehaviorInput, value: str) -> bool:
    return any(
        value.lower().rstrip(".") in {h.lower().rstrip(".") for h in a.hosts}
        for a in _authorities(ctx)
    )


def _rule001(c: BehaviorInput) -> WatchMatch:
    hits = tuple(
        e
        for e in c.evidence
        if e.certain
        and (
            e.kind in {"leak", "network", "write", "process", "stderr"}
            and (e.kind == "leak" or e.value in c.decoys)
        )
    )
    return _result("WATCH-001", OutcomeState.MATCH if hits else OutcomeState.CLEAR, hits)


def _rule002(c: BehaviorInput) -> WatchMatch:
    candidates = tuple(
        e for e in c.evidence if e.kind in {"file", "read"} and e.operation in {"read", "open", ""}
    )
    if any(not e.certain for e in candidates):
        return _result("WATCH-002", OutcomeState.UNKNOWN, candidates, "INCOMPLETE_EVIDENCE")
    hits = tuple(e for e in candidates if e.value in c.decoys and not _declared_path(c, e.value))
    return _result("WATCH-002", OutcomeState.MATCH if hits else OutcomeState.CLEAR, hits)


def _rule003(c: BehaviorInput) -> WatchMatch:
    nets = tuple(
        e
        for e in c.evidence
        if e.kind in _NETWORK and e.operation in {"connect", "request", "post", ""}
    )
    if not nets:
        return _result("WATCH-003", OutcomeState.CLEAR)
    if any(not e.certain for e in nets) or not _authorities(c):
        return _result("WATCH-003", OutcomeState.UNKNOWN, nets, "INCOMPLETE_EVIDENCE")
    hits = tuple(e for e in nets if not _declared_host(c, e.value) and not host_allowed(e.value))
    return _result("WATCH-003", OutcomeState.MATCH if hits else OutcomeState.CLEAR, nets)


def _span_rule(c: BehaviorInput, rule: str, kind: str) -> WatchMatch:
    hits = tuple(
        e
        for e in c.evidence
        if e.kind in _NETWORK and e.span_kind is not None and e.span_kind.value == kind
    )
    return _result(rule, OutcomeState.MATCH if hits else OutcomeState.CLEAR, hits)


def _rule005(c: BehaviorInput) -> WatchMatch:
    candidates = tuple(
        e
        for e in c.evidence
        if e.kind in _NETWORK and e.span_kind is not None and e.span_kind.value == "install"
    )
    if any(not e.certain for e in candidates):
        return _result("WATCH-005", OutcomeState.UNKNOWN, candidates, "INCOMPLETE_EVIDENCE")
    hits = tuple(e for e in candidates if not host_allowed(e.value, install=True))
    return _result("WATCH-005", OutcomeState.MATCH if hits else OutcomeState.CLEAR, candidates)


def _rule006(c: BehaviorInput) -> WatchMatch:
    candidates = tuple(
        e
        for e in c.evidence
        if e.kind in {"file", "read"} and any(n in e.value for n in _CONFIG_NAMES)
    )
    if any(not e.certain for e in candidates):
        return _result("WATCH-006", OutcomeState.UNKNOWN, candidates, "INCOMPLETE_EVIDENCE")
    hits = tuple(e for e in candidates if not _declared_path(c, e.value))
    return _result("WATCH-006", OutcomeState.MATCH if hits else OutcomeState.CLEAR, hits)


def _rule007(c: BehaviorInput) -> WatchMatch:
    hits = tuple(e for e in c.evidence if e.kind == "proxy" and e.operation.upper() == "DROP")
    return _result("WATCH-007", OutcomeState.MATCH if hits else OutcomeState.CLEAR, hits)


def _rule008(c: BehaviorInput) -> WatchMatch:
    hits = tuple(
        e
        for e in c.evidence
        if e.kind == "process"
        and not any(x in e.value.lower() for x in _TOOLING)
        and not any(e.value == p for a in _authorities(c) for p in a.processes)
    )
    return _result("WATCH-008", OutcomeState.MATCH if hits else OutcomeState.CLEAR, hits)


def _rule009(c: BehaviorInput) -> WatchMatch:
    values = tuple(
        e.value for e in c.evidence if e.kind in {"stat", "read"} or e.operation in {"stat", "read"}
    )
    hit = broad_enumeration_count(values) >= 10
    return _result("WATCH-009", OutcomeState.MATCH if hit else OutcomeState.CLEAR)


def _rule010(c: BehaviorInput) -> WatchMatch:
    auth = _authorities(c)
    if not auth or any(a.coverage is not CoverageState.COMPLETE for a in auth):
        return _result("WATCH-010", OutcomeState.UNKNOWN, reason="INCOMPLETE_DECLARATION")
    if any(not e.certain for e in c.evidence):
        return _result("WATCH-010", OutcomeState.UNKNOWN, reason="INCOMPLETE_EVIDENCE")
    unmatched = tuple(
        e
        for e in c.evidence
        if (e.kind in {"file", "read", "write"} and not _declared_path(c, e.value))
        or (e.kind in _NETWORK and not _declared_host(c, e.value))
    )
    return _result("WATCH-010", OutcomeState.CLEAR if unmatched else OutcomeState.MATCH, unmatched)


def _rule011(c: BehaviorInput) -> WatchMatch:
    withheld = (
        c.withheld
        or not c.authorities
        or any(a.coverage is not CoverageState.COMPLETE for a in c.authorities)
    )
    return _result(
        "WATCH-011",
        OutcomeState.MATCH if withheld else OutcomeState.CLEAR,
        reason="DECLARATION_INCOMPLETE" if withheld else "",
    )


def _rule012(c: BehaviorInput) -> WatchMatch:
    hits = tuple(
        e for e in c.evidence if e.kind == "url" and e.value.startswith(("http://", "https://"))
    )
    return _result(
        "WATCH-012", OutcomeState.MATCH if many_urls(len(hits)) else OutcomeState.CLEAR, hits
    )


def _rule013(c: BehaviorInput) -> WatchMatch:
    readonly = tuple(a for a in c.authorities if a.read_only_hint is True)
    if not readonly:
        return _result("WATCH-013", OutcomeState.CLEAR)
    hits = tuple(
        e for e in c.evidence if e.kind in {"write", "network"} and (e.kind == "write" or e.post)
    )
    return _result("WATCH-013", OutcomeState.MATCH if hits else OutcomeState.CLEAR, hits)


def _rule014(c: BehaviorInput) -> WatchMatch:
    return _span_rule(c, "WATCH-014", "startup")


_HANDLERS: tuple[Callable[[BehaviorInput], WatchMatch], ...] = (
    _rule001,
    _rule002,
    _rule003,
    lambda c: _span_rule(c, "WATCH-004", "idle"),
    _rule005,
    _rule006,
    _rule007,
    _rule008,
    _rule009,
    _rule010,
    _rule011,
    _rule012,
    _rule013,
    _rule014,
)


def evaluate(context: BehaviorInput) -> tuple[WatchMatch, ...]:
    """Evaluate all rules in catalog order; absence produces CLEAR, not a match."""
    return tuple(handler(context) for handler in _HANDLERS)


def evaluate_rule(rule_id: str, context: BehaviorInput) -> WatchMatch:
    index = next((i for i, rule in enumerate(RULE_CATALOG) if rule.rule_id == rule_id), -1)
    if index < 0:
        raise KeyError(rule_id)
    return _HANDLERS[index](context)


__all__ = ["evaluate", "evaluate_rule"]
