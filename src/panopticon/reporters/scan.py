"""SARIF rendering and persistence for typed scan outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from panopticon.engine.scan import ScanFinding, ScanOutcome
from panopticon.store.contracts import PersistResult, PersistSuccess
from panopticon.util.leak_check import LeakContext

from .model import from_result
from .persist import ReportFormat, persist_report
from .report_bundle import ReportBundle, ReportFinding, bundle
from .sarif import render_sarif


@dataclass(frozen=True, slots=True)
class RenderedScan:
    stdout: str
    stderr: str
    exit_code: int


def _finding(finding: ScanFinding) -> ReportFinding:
    return ReportFinding(
        finding.rule_id,
        finding.title,
        finding.severity,
        finding.fingerprint,
        finding.path,
        finding.line,
        finding.column,
        finding.kind,
    )


def make_bundle(outcome: ScanOutcome) -> ReportBundle:
    findings = tuple(_finding(finding) for finding in outcome.findings)
    return bundle(from_result(outcome.result), findings, category="scan")


def render(outcome: ScanOutcome) -> str:
    return render_sarif(make_bundle(outcome))


def render_cli(outcome: ScanOutcome, *, sarif: bool = False) -> RenderedScan:
    if sarif:
        return RenderedScan(render(outcome), "", outcome.exit_code)
    lines = [
        f"scan: {outcome.status.value} mode={outcome.mode.value} findings={len(outcome.findings)}"
    ]
    lines.extend(
        f"{finding.rule_id} {finding.severity} {finding.path or '-'}"
        for finding in outcome.findings
    )
    text = "\n".join(lines) + "\n"
    if outcome.exit_code == 3:
        return RenderedScan("", text, outcome.exit_code)
    return RenderedScan(text, "", outcome.exit_code)


def persist(
    outcome: ScanOutcome,
    target: Path,
    leak_context: LeakContext | None = None,
) -> PersistResult:
    return persist_report(
        target,
        make_bundle(outcome),
        ReportFormat.SARIF,
        leak_context or LeakContext(home_paths=(str(Path.home()),)),
    )


def persist_succeeded(result: PersistResult) -> bool:
    return isinstance(result, PersistSuccess)


__all__ = [
    "RenderedScan",
    "make_bundle",
    "persist",
    "persist_succeeded",
    "render",
    "render_cli",
]
