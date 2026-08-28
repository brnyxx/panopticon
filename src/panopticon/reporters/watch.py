"""Sanitized deterministic renderer for multi-target watch outcomes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from panopticon.engine.contracts import Result
from panopticon.engine.exit_codes import result_exit_code
from panopticon.engine.watch_service import WatchServiceOutcome, WatchTargetReceipt
from panopticon.reporters.base import Render
from panopticon.util.leak_check import LeakContext, find_leaks


@dataclass(frozen=True, slots=True)
class WatchTargetView:
    name: str
    status: str
    reason_code: str
    artifact_path: str | None
    observation_count: int
    evidence_count: int
    finding_count: int
    suppression_count: int
    excluded_allowlist_count: int
    findings: tuple[tuple[str, str, str, bool], ...]
    coverage: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True, slots=True)
class WatchRenderModel:
    status: str
    reason_code: str
    targets: tuple[WatchTargetView, ...]
    diagnostics: tuple[tuple[str, str], ...]


def _target(receipt: WatchTargetReceipt) -> WatchTargetView:
    coverage = tuple(sorted(receipt.coverage))
    if not coverage:
        coverage = tuple(
            (name, "UNKNOWN", "UNKNOWN")
            for name in ("dns", "file", "net", "process", "proxy", "snapshot", "stdio")
        )
    return WatchTargetView(
        receipt.name,
        receipt.status,
        receipt.reason_code,
        receipt.observation_path,
        receipt.observation_count,
        receipt.evidence_count,
        receipt.finding_count,
        receipt.suppression_count,
        receipt.excluded_allowlist_count,
        tuple(sorted(receipt.findings)),
        coverage,
    )


def from_outcome(outcome: WatchServiceOutcome) -> WatchRenderModel:
    result: Result = outcome.result
    context = LeakContext(home_paths=(str(Path.home()),))
    if find_leaks(repr(outcome), context):
        raise ValueError("report input contains prohibited evidence")
    return WatchRenderModel(
        result.status.value,
        result.reason_code.value,
        tuple(sorted((_target(item) for item in outcome.targets), key=lambda item: item.name)),
        tuple(sorted((item.code, item.detail) for item in result.diagnostics)),
    )


def _payload(model: WatchRenderModel) -> dict[str, object]:
    return {
        "status": model.status,
        "reason_code": model.reason_code,
        "targets": [
            {
                "name": target.name,
                "status": target.status,
                "reason_code": target.reason_code,
                "artifact_path": target.artifact_path,
                "observation_count": target.observation_count,
                "evidence_count": target.evidence_count,
                "finding_count": target.finding_count,
                "suppression_count": target.suppression_count,
                "excluded_allowlist_count": target.excluded_allowlist_count,
                "findings": [
                    {
                        "rule_id": rule_id,
                        "severity": severity,
                        "title": title,
                        "suppressed": suppressed,
                    }
                    for rule_id, severity, title, suppressed in target.findings
                ],
                "coverage": [
                    {"name": name, "status": status, "reason_code": reason}
                    for name, status, reason in target.coverage
                ],
            }
            for target in model.targets
        ],
        "diagnostics": [{"code": code, "detail": detail} for code, detail in model.diagnostics],
    }


def render(outcome: WatchServiceOutcome, *, json_output: bool) -> Render:
    try:
        model = from_outcome(outcome)
    except ValueError:
        return Render(stdout="", stderr="", exit_code=1)
    exit_code = result_exit_code(outcome.result)
    if json_output:
        text = (
            json.dumps(_payload(model), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            + "\n"
        )
    else:
        lines = [f"Status: {model.status}", f"Reason: {model.reason_code}"]
        for target in model.targets:
            artifact = target.artifact_path or "-"
            lines.extend(
                (
                    f"Target: {target.name}",
                    f"  Status: {target.status} ({target.reason_code})",
                    f"  Artifact: {artifact}",
                )
            )
            lines.append(f"  Observations: {target.observation_count}")
            lines.append(f"  Evidence: {target.evidence_count}")
            lines.append(f"  Findings: {target.finding_count}")
            lines.append(f"  Suppressed: {target.suppression_count}")
            lines.append(f"  Allowlist-excluded: {target.excluded_allowlist_count}")
            if target.findings:
                lines.append("  Findings:")
                for rule_id, severity, title, suppressed in target.findings:
                    suffix = " [SUPPRESSED]" if suppressed else ""
                    lines.append(f"    {rule_id} {severity}: {title}{suffix}")
            lines.append("  Coverage:")
            for name, status, reason in target.coverage:
                lines.append(f"    {name}: {status} ({reason})")
            if not target.coverage:
                lines.append("    UNKNOWN")
        if model.diagnostics:
            lines.append("Diagnostics: " + ", ".join(code for code, _ in model.diagnostics))
        text = "\n".join(lines) + "\n"
    return Render(stdout=text, stderr="", exit_code=exit_code)


__all__ = ["WatchRenderModel", "WatchTargetView", "from_outcome", "render"]
