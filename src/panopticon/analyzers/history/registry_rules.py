"""Register executable HIST analyzers with the global rule registry."""

from __future__ import annotations

from collections.abc import Iterable

from panopticon.findings.build import FindingDraft, build_finding
from panopticon.models.finding import EvidenceKind, Finding, FindingEvidence
from panopticon.rules.context import RuleContext, SourceStatus
from panopticon.rules.registry import Kind, RuleFn, RuleMeta, Severity, rule

from .catalog import RULES
from .model import HistoryRuleInput, HistoryStatus
from .rules import evaluate_rule

_SEVERITY: dict[str, Severity] = {"HIGH": "HIGH", "MEDIUM": "MEDIUM", "INFO": "INFO"}
_KIND: dict[str, Kind] = {"review": "review", "info": "info"}
_registered = False


def _findings(rule_id: str, context: RuleContext) -> Iterable[Finding]:
    if context.history.status is not SourceStatus.AVAILABLE:
        return ()
    value = context.history.value
    if not isinstance(value, HistoryRuleInput):
        return ()
    outcome = evaluate_rule(rule_id, value.series, now=value.observed_at)
    if outcome.status is not HistoryStatus.FINDING:
        return ()
    metadata = next(item for item in RULES if item.rule_id == rule_id)
    meta = RuleMeta(
        id=rule_id,
        severity=_SEVERITY[metadata.severity.value],
        kind=_KIND[metadata.kind.value],
        line="history",
    )
    evidence = tuple(
        FindingEvidence(
            kind=EvidenceKind.CONFIG,
            subject=item.subject,
            value=item.classification,
        )
        for item in outcome.evidence
    )
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
    for metadata in RULES:
        rule(
            rule_id=metadata.rule_id,
            severity=_SEVERITY[metadata.severity.value],
            kind=_KIND[metadata.kind.value],
            line="history",
        )(_handler(metadata.rule_id))
    _registered = True


__all__ = ["register_rules"]
