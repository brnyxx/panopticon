"""Deterministic SARIF 2.1.0 renderer."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from urllib.parse import quote

from panopticon.models.finding import Finding
from panopticon.reporters.base import Render
from panopticon.reporters.escaping import artifact_uri
from panopticon.reporters.model import SanitizedRenderModel
from panopticon.reporters.report_bundle import ReportBundle, ReportFinding, bundle
from panopticon.reporters.rule_metadata import metadata_map

SCHEMA_URI = (
    "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json"
)
SARIF_SCHEMA_URI = SCHEMA_URI


def _level(severity: str) -> str:
    return {"HIGH": "error", "MEDIUM": "warning", "LOW": "note", "INFO": "note"}.get(
        str(severity).upper(), "none"
    )


def _result(f: ReportFinding, rule_index: dict[str, int]) -> dict[str, object]:
    result: dict[str, object] = {
        "ruleId": f.rule_id,
        "ruleIndex": rule_index[f.rule_id],
        "level": _level(f.severity),
        "message": {"text": f.title},
        "properties": {"kind": f.kind, "suppressed": f.suppressed, "fixAvailable": f.fix_available},
    }
    if f.path:
        region: dict[str, int] = {}
        if f.line is not None:
            region["startLine"] = max(1, f.line)
        if f.column is not None:
            region["startColumn"] = max(1, f.column)
        result["locations"] = [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": artifact_uri(f.path)},
                    "region": region,
                }
            }
        ]
    if f.logical_key:
        digest = hashlib.sha256(f.logical_key.encode("utf-8", "strict")).hexdigest()
        result["partialFingerprints"] = {"panopticon/v1": digest}
    if f.suppressed:
        result["suppressions"] = [{"kind": "inSource", "status": "accepted"}]
    return result


def payload(report: ReportBundle) -> dict[str, object]:
    ids = [f.rule_id for f in report.findings]
    metadata = metadata_map(ids)
    index = {m.id: i for i, m in enumerate(metadata)}
    rules = [
        {
            "id": m.id,
            "name": m.name,
            "shortDescription": {"text": m.description},
            **({"helpUri": m.help_uri} if m.help_uri else {}),
        }
        for m in metadata
    ]
    notifications = []
    for stage in report.model.stages:
        if stage.status.upper() in {"INCOMPLETE", "UNSUPPORTED", "UNKNOWN"}:
            notifications.append(
                {
                    "level": "warning",
                    "message": {
                        "text": f"Coverage {stage.name}: {stage.status} ({stage.reason_code})"
                    },
                }
            )
    run = {
        "tool": {"driver": {"name": "Panopticon", "version": "1", "rules": rules}},
        "automationDetails": {"id": quote(report.category, safe="/._-")},
        "results": [_result(f, index) for f in report.findings],
        "invocations": [
            {
                "executionSuccessful": report.model.status.upper() != "FAILED",
                "toolExecutionNotifications": notifications,
            }
        ],
    }
    return {"$schema": SCHEMA_URI, "version": "2.1.0", "runs": [run]}


def render_sarif(
    report: ReportBundle | SanitizedRenderModel,
    findings: Iterable[Finding | ReportFinding] = (),
    *,
    category: str = "panopticon",
) -> str:
    report = (
        report if isinstance(report, ReportBundle) else bundle(report, findings, category=category)
    )
    return (
        json.dumps(payload(report), ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    )


def render(
    report: ReportBundle | SanitizedRenderModel,
    findings: Iterable[Finding | ReportFinding] = (),
    *,
    category: str = "panopticon",
    exit_code: int = 0,
) -> Render:
    return Render(render_sarif(report, findings, category=category), "", exit_code)


__all__ = ["SARIF_SCHEMA_URI", "payload", "render", "render_sarif"]
