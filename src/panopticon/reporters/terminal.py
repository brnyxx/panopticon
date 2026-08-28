"""Deterministic terminal and plain-text reporter."""

from __future__ import annotations

from panopticon.engine.contracts import Result
from panopticon.engine.exit_codes import result_exit_code
from panopticon.reporters.base import Render
from panopticon.reporters.model import SanitizedRenderModel, from_result

_LABELS = {
    "en": {
        "status": "Status",
        "reason": "Reason",
        "coverage": "Coverage",
        "diagnostics": "Diagnostics",
        "excluded": "Excluded",
        "suppressed": "Suppressed",
        "evidence": "Evidence",
    },
    "ko": {
        "status": "상태",
        "reason": "사유",
        "coverage": "범위",
        "diagnostics": "진단",
        "excluded": "제외",
        "suppressed": "억제",
        "evidence": "근거",
    },
}


def render_model(
    model: SanitizedRenderModel, *, tty: bool = False, locale: str = "en", exit_code: int = 0
) -> Render:
    labels = _LABELS.get(locale, _LABELS["en"])
    lines = [f"{labels['status']}: {model.status}", f"{labels['reason']}: {model.reason_code}"]
    lines.append(f"{labels['coverage']}:")
    for stage in model.stages:
        lines.append(f"  {stage.name}: {stage.status} ({stage.reason_code})")
    lines.extend(
        (
            f"{labels['evidence']}: {model.evidence_count}",
            f"{labels['excluded']}: {model.excluded_allowlist_count}",
            f"{labels['suppressed']}: {model.suppression_count}",
        )
    )
    if model.diagnostics:
        lines.append(f"{labels['diagnostics']}: " + ", ".join(model.diagnostics))
    text = "\n".join(lines) + "\n"
    if tty:
        text = f"\033[1m{text}\033[0m"
    return Render(stdout=text, stderr="", exit_code=exit_code)


def render(
    result: Result, *, tty: bool = False, locale: str = "en", json_output: bool = False
) -> Render:
    if json_output:
        from panopticon.reporters.json import render as json_render

        return json_render(result)
    try:
        model = from_result(result)
    except ValueError:
        return Render(stdout="", stderr="", exit_code=1)
    return render_model(model, tty=tty, locale=locale, exit_code=result_exit_code(result))


class TerminalReporter:
    def render(
        self, result: Result, *, tty: bool = False, locale: str = "en", json_output: bool = False
    ) -> Render:
        return render(result, tty=tty, locale=locale, json_output=json_output)


__all__ = ["TerminalReporter", "render", "render_model"]
