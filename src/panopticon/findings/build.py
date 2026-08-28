"""Construction of immutable findings and deterministic occurrence identities."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from panopticon.models.finding import (
    EvidenceKind,
    Finding,
    FindingEvidence,
    FindingKind,
    FindingSeverity,
    SourceLocation,
)
from panopticon.models.ids import (
    FindingId,
    InstallationId,
    ObservationId,
    ServerId,
    SpanId,
    derive_logical_key,
)
from panopticon.rules.registry import RuleMeta


def normalize_evidence(
    evidence: Iterable[FindingEvidence | Mapping[str, object]],
) -> tuple[FindingEvidence, ...]:
    """Normalize evidence values for stable IDs and persistence."""
    result: list[FindingEvidence] = []
    for item in evidence:
        if isinstance(item, FindingEvidence):
            raw = item
        else:
            kind = item.get("kind")
            subject = item.get("subject")
            value = item.get("value")
            if (
                not isinstance(kind, str)
                or not isinstance(subject, str)
                or not isinstance(value, str)
            ):
                raise ValueError("finding evidence requires string kind, subject, and value")
            raw = FindingEvidence(
                kind=EvidenceKind(kind),
                subject=subject,
                value=value,
            )
        value = raw.value
        if raw.kind is EvidenceKind.PATH:
            value = re.sub(
                r"^(?:[A-Za-z]:)?(?:/Users/[^/]+|/home/[^/]+)", "~", value.replace("\\", "/")
            )
        elif raw.kind is EvidenceKind.HOST:
            parsed = urlsplit(value if "://" in value else f"//{value}")
            host = (parsed.hostname or value).casefold()
            try:
                port = parsed.port
            except ValueError:
                port = None
            value = host if port in (None, 80, 443) else f"{host}:{port}"
        result.append(FindingEvidence(kind=raw.kind, subject=raw.subject, value=value))
    return tuple(sorted(result, key=lambda x: (x.kind.value, x.subject, x.value)))


def occurrence_id(
    rule_id: str, installation_id: InstallationId, evidence: Iterable[FindingEvidence]
) -> str:
    normalized = normalize_evidence(evidence)
    payload = json.dumps(
        [(e.kind.value, e.subject, e.value) for e in normalized],
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(f"{rule_id}|{installation_id}|{payload}".encode()).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class FindingDraft:
    meta: RuleMeta
    server_id: ServerId
    installation_id: InstallationId
    observation_id: ObservationId
    subject: str
    title: str
    evidence: tuple[FindingEvidence | Mapping[str, object], ...]
    first_seen: datetime
    location: SourceLocation | None = None
    span_ref: SpanId | None = None
    declared_source: str | None = None
    remediation_key: str | None = None
    suppressed_by: str | None = None


def build_finding(draft: FindingDraft) -> Finding:
    normalized = normalize_evidence(draft.evidence)
    return Finding(
        schema_version="1.0",
        id=FindingId(occurrence_id(draft.meta.id, draft.installation_id, normalized)),
        logical_key=derive_logical_key(
            draft.meta.id,
            draft.installation_id,
            draft.subject,
        ),
        rule_id=draft.meta.id,
        severity=FindingSeverity(draft.meta.severity) if draft.meta.severity else None,
        kind=FindingKind(draft.meta.kind),
        title=draft.title,
        evidence=normalized,
        location=draft.location,
        server_id=draft.server_id,
        installation_id=draft.installation_id,
        observation_id=draft.observation_id,
        span_ref=draft.span_ref,
        remediation_key=draft.remediation_key,
        fix_available=draft.meta.fix_id is not None,
        declared_source=draft.declared_source,
        first_seen=draft.first_seen,
        suppressed_by=draft.suppressed_by,
    )
