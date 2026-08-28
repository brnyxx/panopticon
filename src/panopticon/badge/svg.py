"""Accessible deterministic SVG evidence-badge renderer."""

from __future__ import annotations

from html import escape

from .eligibility import badge_eligible
from .model import EvidenceCardModel


class BadgeIneligibleError(ValueError):
    """The observation does not satisfy evidence-badge prerequisites."""


def render_svg(model: EvidenceCardModel) -> str:
    if not badge_eligible(model):
        raise BadgeIneligibleError("BADGE_INELIGIBLE")
    label = "DECLARED = OBSERVED" if model.locale == "en" else "선언 = 관찰"
    title = "Panopticon evidence badge" if model.locale == "en" else "Panopticon 관찰 근거 badge"
    description = (
        f"Observation date {model.observed_on.isoformat()}; "
        f"coverage {model.overall_coverage.value}."
    )
    label_value = escape(label, quote=True)
    date_value = escape(model.observed_on.isoformat(), quote=True)
    coverage_value = escape(model.overall_coverage.value, quote=True)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="260" height="64" '
        'viewBox="0 0 260 64" role="img" aria-labelledby="title desc">'
        f'<title id="title">{escape(title, quote=True)}</title>'
        f'<desc id="desc">{escape(description, quote=True)}</desc>'
        '<rect width="260" height="64" rx="8" fill="#0f172a"/>'
        '<rect width="6" height="64" rx="3" fill="#2dd4bf"/>'
        f'<text x="20" y="28" fill="#f1f5f9" font-family="NanumGothic" '
        f'font-size="14">{label_value}</text>'
        f'<text x="20" y="48" fill="#94a3b8" font-family="NanumGothic" '
        f'font-size="11">{date_value} · {coverage_value}</text>'
        "</svg>\n"
    )


class SVGReporter:
    name = "svg"

    def render(self, model: EvidenceCardModel) -> str:
        return render_svg(model)


__all__ = ["BadgeIneligibleError", "SVGReporter", "render_svg"]
