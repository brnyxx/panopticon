"""Deterministic terminal and plain-text reporter."""

from __future__ import annotations

from panopticon.reporters.base import Render
from panopticon.reporters.model import SanitizedRenderModel

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
    model: SanitizedRenderModel,
    *,
    tty: bool = False,
    locale: str = "en",
    exit_code: int = 0,
) -> Render:
    labels = _LABELS.get(locale, _LABELS["en"])
    lines = [f"{labels['status']}: {model.status}", f"{labels['reason']}: {model.reason_code}"]
    lines.append(f"{labels['coverage']}:")
    for stage in sorted(model.stages, key=lambda item: item.name):
        lines.append(f"  {stage.name}: {stage.status} ({stage.reason_code})")
    lines.extend(
        (
            f"{labels['evidence']}: {model.evidence_count}",
            f"{labels['excluded']}: {model.excluded_allowlist_count}",
            f"{labels['suppressed']}: {model.suppression_count}",
        )
    )
    if model.diagnostics:
        lines.append(
            f"{labels['diagnostics']}: "
            + ", ".join(diagnostic.code for diagnostic in model.diagnostics)
        )
    text = "\n".join(lines) + "\n"
    if tty:
        text = f"\033[1m{text}\033[0m"
    return Render(stdout=text, stderr="", exit_code=exit_code)


class TerminalReporter:
    def __init__(self, *, tty: bool = False, locale: str = "en", exit_code: int = 0) -> None:
        self.tty = tty
        self.locale = locale
        self.exit_code = exit_code

    def render(self, model: SanitizedRenderModel) -> Render:
        return render_model(
            model,
            tty=self.tty,
            locale=self.locale,
            exit_code=self.exit_code,
        )


__all__ = ["TerminalReporter", "render_model"]
