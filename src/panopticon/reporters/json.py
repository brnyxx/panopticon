"""Canonical machine-readable JSON reporter."""

from __future__ import annotations

import json
from typing import Any

from panopticon.engine.contracts import Result
from panopticon.engine.exit_codes import result_exit_code
from panopticon.reporters.base import Render
from panopticon.reporters.model import SanitizedRenderModel, from_result


def payload(model: SanitizedRenderModel) -> dict[str, Any]:
    return {
        "coverage": [
            {
                "name": s.name,
                "status": s.status,
                "reason_code": s.reason_code,
                "diagnostics": list(s.diagnostics),
            }
            for s in sorted(model.stages, key=lambda item: item.name)
        ],
        "diagnostics": list(model.diagnostics),
        "evidence_count": model.evidence_count,
        "excluded_count": model.excluded_count,
        "excluded_allowlist_count": model.excluded_allowlist_count,
        "reason_code": model.reason_code,
        "status": model.status,
        "suppressed_count": model.suppressed_count,
        "suppression_count": model.suppression_count,
    }


def render_model(model: SanitizedRenderModel, *, exit_code: int = 0) -> Render:
    text = (
        json.dumps(payload(model), ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    )
    return Render(stdout=text, stderr="", exit_code=exit_code)


def render(result: Result | SanitizedRenderModel, *, json_output: bool = True) -> Render:
    if isinstance(result, SanitizedRenderModel):
        return render_model(result)
    try:
        model = from_result(result)
    except ValueError:
        return Render(stdout="", stderr="", exit_code=1)
    return render_model(model, exit_code=result_exit_code(result))


class JsonReporter:
    def render(self, result: Result, *, json_output: bool = True) -> Render:
        return render(result)


__all__ = ["JsonReporter", "payload", "render", "render_model"]
