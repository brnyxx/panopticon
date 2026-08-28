"""Register executable WATCH analyzers with the global rule registry."""

from __future__ import annotations

from collections.abc import Iterable

from panopticon.findings.build import FindingDraft, build_finding
from panopticon.models.finding import EvidenceKind as FindingEvidenceKind
from panopticon.models.finding import Finding, FindingEvidence
from panopticon.models.ids import SpanId
from panopticon.rules.context import RuleContext, SourceStatus
from panopticon.rules.registry import Kind, RuleFn, RuleMeta, Severity, rule

from .catalog import RULE_CATALOG
from .model import BehaviorInput, EvidenceKind, OutcomeState, WatchEvidence
from .rules import evaluate_rule

_KIND: dict[str, Kind] = {"confirmed": "confirmed", "review": "review", "info": "info"}
_SEVERITY: dict[str, Severity | None] = {
    "HIGH": "HIGH",
    "MEDIUM": "MEDIUM",
    "LOW": "LOW",
    "INFO": "INFO",
    "—": None,
}
_registered = False


def _evidence_kind(item: WatchEvidence) -> FindingEvidenceKind:
    if item.kind in {EvidenceKind.FILE, EvidenceKind.READ, EvidenceKind.STAT, EvidenceKind.WRITE}:
        return FindingEvidenceKind.PATH
    if item.kind in {
        EvidenceKind.NETWORK,
        EvidenceKind.DNS,
        EvidenceKind.CONNECT,
        EvidenceKind.REQUEST,
        EvidenceKind.URL,
    }:
        return FindingEvidenceKind.HOST
    if item.kind is EvidenceKind.PROCESS:
        return FindingEvidenceKind.PROCESS
    if item.kind is EvidenceKind.LEAK:
        return FindingEvidenceKind.DECOY
    return FindingEvidenceKind.PROTOCOL


def _finding_evidence(
    items: tuple[WatchEvidence, ...],
    rule_id: str,
) -> tuple[FindingEvidence, ...]:
    values = tuple(
        FindingEvidence(
            kind=_evidence_kind(item),
            subject=item.value,
            value=item.operation or item.kind.value,
        )
        for item in items
    )
    if values:
        return values
    return (
        FindingEvidence(
            kind=FindingEvidenceKind.PROTOCOL,
            subject=rule_id,
            value="complete-declaration" if rule_id == "WATCH-010" else "declaration-withheld",
        ),
    )


def _findings(rule_id: str, context: RuleContext) -> Iterable[Finding]:
    if context.observation.status is not SourceStatus.AVAILABLE:
        return ()
    value = context.observation.value
    if not isinstance(value, BehaviorInput):
        return ()
    if (
        value.server_id is None
        or value.installation_id is None
        or value.observation_id is None
        or value.observed_at is None
    ):
        return ()
    match = evaluate_rule(rule_id, value)
    if match.state not in {OutcomeState.MATCH, OutcomeState.UNKNOWN}:
        return ()
    if match.state is OutcomeState.UNKNOWN and not match.evidence:
        return ()
    catalog = next(item for item in RULE_CATALOG if item.rule_id == rule_id)
    meta = RuleMeta(
        id=rule_id,
        severity=_SEVERITY[catalog.severity],
        kind="review" if match.state is OutcomeState.UNKNOWN else _KIND[catalog.kind],
        line="observe",
    )
    evidence = _finding_evidence(match.evidence, rule_id)
    span_id = next((item.span_id for item in match.evidence if item.span_id), None)
    return (
        build_finding(
            FindingDraft(
                meta=meta,
                server_id=value.server_id,
                installation_id=value.installation_id,
                observation_id=value.observation_id,
                subject=evidence[0].subject,
                title=rule_id,
                evidence=evidence,
                first_seen=value.observed_at,
                span_ref=SpanId(span_id) if span_id is not None else None,
                declared_source="tool" if value.current_tool is not None else None,
                suppressed_by=rule_id if match.suppressed else None,
            )
        ),
    )


def _handler(rule_id: str) -> RuleFn:
    def handler(context: RuleContext) -> Iterable[Finding]:
        return _findings(rule_id, context)

    handler.__name__ = rule_id.replace("-", "_").casefold()
    return handler


def register_rules() -> None:
    global _registered
    if _registered:
        return
    for metadata in RULE_CATALOG:
        rule(
            rule_id=metadata.rule_id,
            severity=_SEVERITY[metadata.severity],
            kind=_KIND[metadata.kind],
            line="observe",
        )(_handler(metadata.rule_id))
    _registered = True


__all__ = ["register_rules"]
