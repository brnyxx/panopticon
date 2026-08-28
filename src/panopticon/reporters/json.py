"""Canonical machine-readable JSON reporter."""

from __future__ import annotations

import json

from panopticon.reporters.base import Render
from panopticon.reporters.model import SanitizedRenderModel


def payload(model: SanitizedRenderModel) -> dict[str, object]:
    return {
        "coverage": [
            {
                "name": stage.name,
                "status": stage.status,
                "reason_code": stage.reason_code,
                "diagnostics": [
                    {"code": diagnostic.code, "detail": diagnostic.detail}
                    for diagnostic in stage.diagnostics
                ],
            }
            for stage in sorted(model.stages, key=lambda item: item.name)
        ],
        "diagnostics": [
            {"code": diagnostic.code, "detail": diagnostic.detail}
            for diagnostic in model.diagnostics
        ],
        "evidence_count": model.evidence_count,
        "excluded_allowlist_count": model.excluded_allowlist_count,
        "reason_code": model.reason_code,
        "status": model.status,
        "suppression_count": model.suppression_count,
    }


def render_model(model: SanitizedRenderModel, *, exit_code: int = 0) -> Render:
    text = (
        json.dumps(payload(model), ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    )
    return Render(stdout=text, stderr="", exit_code=exit_code)


class JsonReporter:
    def __init__(self, *, exit_code: int = 0) -> None:
        self.exit_code = exit_code

    def render(self, model: SanitizedRenderModel) -> Render:
        return render_model(model, exit_code=self.exit_code)


__all__ = ["JsonReporter", "payload", "render_model"]
