"""Deterministic coverage-aware diff rendering."""

from __future__ import annotations

import json

from panopticon.engine.diff import DiffOutcome
from panopticon.engine.exit_codes import result_exit_code
from panopticon.reporters.base import Render


def render(outcome: DiffOutcome, *, json_output: bool = False) -> Render:
    payload = {
        "status": outcome.result.status.value,
        "reason_code": outcome.result.reason_code.value,
        "diff": outcome.diff.model_dump(mode="json") if outcome.diff is not None else None,
        "diagnostics": [
            {"code": item.code, "detail": item.detail} for item in outcome.result.diagnostics
        ],
    }
    if json_output:
        return Render(
            stdout=json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            stderr="",
            exit_code=result_exit_code(outcome.result),
        )
    lines: list[str] = []
    if outcome.diff is not None:
        sections = (
            ("findings.new", outcome.diff.findings.new),
            ("findings.changed", outcome.diff.findings.changed),
            ("findings.resolved", outcome.diff.findings.resolved),
            ("findings.unknown", outcome.diff.findings.unknown),
            ("capability", outcome.diff.capability),
            ("behavior", outcome.diff.behavior),
            ("inventory", outcome.diff.inventory),
        )
        for section, entries in sections:
            for entry in entries:
                lines.append(f"{section} {entry.kind} {entry.installation_id} {entry.key}")
    for diagnostic in outcome.result.diagnostics:
        lines.append(f"{diagnostic.code}: {diagnostic.detail}")
    return Render(
        stdout="\n".join(lines) + ("\n" if lines else ""),
        stderr="",
        exit_code=result_exit_code(outcome.result),
    )


__all__ = ["render"]
