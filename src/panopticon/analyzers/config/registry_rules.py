"""Register executable CFG analyzers with the global rule registry."""

from __future__ import annotations

from collections.abc import Iterable

from panopticon.findings.build import FindingDraft, build_finding
from panopticon.models.finding import EvidenceKind, Finding, FindingEvidence
from panopticon.rules.context import RuleContext, SourceStatus
from panopticon.rules.registry import Kind, RuleFn, RuleMeta, Severity, rule

from .catalog import RULE_CATALOG
from .model import ConfigInput
from .rules import analyze

_SEVERITY: dict[str, Severity] = {
    "HIGH": "HIGH",
    "MEDIUM": "MEDIUM",
    "LOW": "LOW",
    "INFO": "INFO",
}
_KIND: dict[str, Kind] = {"confirmed": "confirmed", "review": "review", "info": "info"}
_registered = False


def _findings(rule_id: str, context: RuleContext) -> Iterable[Finding]:
    if context.config.status is not SourceStatus.AVAILABLE:
        return ()
    value = context.config.value
    if not isinstance(value, ConfigInput):
        return ()
    if value.observation_id is None or value.observed_at is None:
        return ()
    servers = {str(server.installation_id): server for server in value.servers}
    produced: list[Finding] = []
    for match in analyze(value):
        if match.rule_id != rule_id:
            continue
        server = servers[match.installation_id]
        meta = RuleMeta(
            id=match.rule_id,
            severity=_SEVERITY[match.severity.value],
            kind=_KIND[match.kind.value],
            line="config",
            fix_id=match.fix_id,
        )
        evidence = tuple(
            FindingEvidence(
                kind=EvidenceKind.CONFIG,
                subject=item.subject,
                value=item.classification,
            )
            for item in match.evidence
        )
        produced.append(
            build_finding(
                FindingDraft(
                    meta=meta,
                    server_id=server.server_id,
                    installation_id=server.installation_id,
                    observation_id=value.observation_id,
                    subject=evidence[0].subject,
                    title=match.rule_id,
                    evidence=evidence,
                    first_seen=value.observed_at,
                    remediation_key=match.fix_id,
                )
            )
        )
    return tuple(produced)


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
            severity=_SEVERITY[metadata.severity.value],
            kind=_KIND[metadata.kind.value],
            line="config",
            fix_id=metadata.fix_id,
        )(_handler(metadata.rule_id))
    _registered = True


__all__ = ["register_rules"]
