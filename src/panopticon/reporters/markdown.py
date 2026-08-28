"""Deterministic, injection-safe Markdown renderer."""

from __future__ import annotations

from collections.abc import Iterable

from panopticon.models.finding import Finding
from panopticon.reporters.base import Render
from panopticon.reporters.escaping import markdown as esc
from panopticon.reporters.model import SanitizedRenderModel
from panopticon.reporters.report_bundle import ReportBundle, ReportFinding, bundle


def render_markdown(
    report: ReportBundle | SanitizedRenderModel,
    findings: Iterable[Finding | ReportFinding] = (),
    *,
    category: str = "panopticon",
) -> str:
    report = (
        report if isinstance(report, ReportBundle) else bundle(report, findings, category=category)
    )
    model = report.model
    lines = [
        "# Panopticon report",
        "",
        f"**Status:** {esc(model.status)}  ",
        f"**Reason:** {esc(model.reason_code)}",
        "",
        "## Coverage",
        "",
        "| Stage | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for stage in model.stages:
        lines.append(f"| {esc(stage.name)} | {esc(stage.status)} | {esc(stage.reason_code)} |")
    lines.extend(
        [
            "",
            "## Findings",
            "",
            "| Rule | Severity | Finding | Location | State |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for finding in report.findings:
        location = (
            "—"
            if not finding.path
            else esc(f"{finding.path}:{finding.line or 1}:{finding.column or 1}")
        )
        state = "suppressed" if finding.suppressed else "visible"
        row = (
            f"| {esc(finding.rule_id)} | {esc(finding.severity)} | "
            f"{esc(finding.title)} | {location} | {esc(state)} |"
        )
        lines.append(row)
    suppressed = model.suppression_count + sum(
        1 for finding in report.findings if finding.suppressed
    )
    lines.extend(
        [
            "",
            "## Suppressions and exclusions",
            "",
            f"- Suppressed findings: {suppressed}",
            f"- Allowlist-excluded evidence: {model.excluded_allowlist_count}",
            f"- Evidence items: {model.evidence_count}",
            "",
        ]
    )
    if model.diagnostics:
        lines.extend(["## Diagnostics", ""])
        for diagnostic in model.diagnostics:
            lines.append(f"- `{esc(diagnostic.code)}`: {esc(diagnostic.detail)}")
        lines.append("")
    return "\n".join(lines)


def render(
    report: ReportBundle | SanitizedRenderModel,
    findings: Iterable[Finding | ReportFinding] = (),
    *,
    category: str = "panopticon",
    exit_code: int = 0,
) -> Render:
    return Render(render_markdown(report, findings, category=category), "", exit_code)


__all__ = ["render", "render_markdown"]
