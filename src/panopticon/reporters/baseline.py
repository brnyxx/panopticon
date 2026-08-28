"""Deterministic baseline command rendering."""

from __future__ import annotations

import json

from panopticon.engine.baseline import BaselineOutcome
from panopticon.engine.exit_codes import result_exit_code
from panopticon.reporters.base import Render


def render(outcome: BaselineOutcome, *, json_output: bool = False) -> Render:
    payload = {
        "status": outcome.result.status.value,
        "reason_code": outcome.result.reason_code.value,
        "baselines": [
            baseline.model_dump(mode="json")
            for baseline in sorted(outcome.baselines, key=lambda item: str(item.baseline_id))
        ],
        "removed": outcome.removed.value if outcome.removed is not None else None,
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
    lines = [
        f"{baseline.baseline_id} {baseline.kind.value} {baseline.label or '-'}"
        for baseline in sorted(outcome.baselines, key=lambda item: str(item.baseline_id))
    ]
    if outcome.removed is not None:
        lines.append(outcome.removed.value)
    for diagnostic in outcome.result.diagnostics:
        lines.append(f"{diagnostic.code}: {diagnostic.detail}")
    return Render(
        stdout="\n".join(lines) + ("\n" if lines else ""),
        stderr="",
        exit_code=result_exit_code(outcome.result),
    )


__all__ = ["render"]
