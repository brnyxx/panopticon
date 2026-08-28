"""Deterministic high-contrast PNG evidence-card renderer."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from panopticon.badge.font import load_font
from panopticon.badge.model import EvidenceCardModel

WIDTH, HEIGHT = 960, 540
BACKGROUND = (15, 23, 42)
FOREGROUND = (241, 245, 249)
ACCENT = (45, 212, 191)
MUTED = (148, 163, 184)
_LABELS = {
    "en": {
        "heading": "PANOPTICON / EVIDENCE",
        "observed": "OBSERVED",
        "coverage": "COVERAGE",
        "declared": "DECLARED",
        "events": "EVENTS UNCOVERED",
        "leaks": "LEAK FINDINGS",
        "findings": "FINDINGS",
        "no_stages": "NO APPLICABLE STAGES",
    },
    "ko": {
        "heading": "PANOPTICON / 관찰 근거",
        "observed": "관찰일",
        "coverage": "COVERAGE",
        "declared": "선언",
        "events": "미포함 이벤트",
        "leaks": "유출 근거",
        "findings": "FINDINGS",
        "no_stages": "적용 가능한 STAGE 없음",
    },
}


def _lines(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
    max_lines: int | None = None,
) -> list[str]:
    result: list[str] = []
    current = ""
    for character in text:
        candidate = current + character
        if current and draw.textlength(candidate, font=font) > max_width:
            result.append(current)
            current = character
        else:
            current = candidate
    if current:
        result.append(current)
    if not result:
        return [""]
    if max_lines is not None and len(result) > max_lines:
        result = result[:max_lines]
        line = result[-1]
        while line and draw.textlength(f"{line}…", font=font) > max_width:
            line = line[:-1]
        result[-1] = f"{line}…"
    return result


def render_png(
    model: EvidenceCardModel,
    *,
    font_path: str | None = None,
    allowed_font_hashes: frozenset[str] | None = None,
) -> bytes:
    """Render stripped PNG bytes without filesystem writes or clock access."""
    font = load_font(28, path=font_path, allowed_hashes=allowed_font_hashes)
    small = load_font(20, path=font_path, allowed_hashes=allowed_font_hashes)
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    labels = _LABELS[model.locale]
    draw.rectangle((0, 0, WIDTH, 10), fill=ACCENT)
    draw.text((48, 38), labels["heading"], font=small, fill=ACCENT)
    y = 78
    for line in _lines(model.server, font, WIDTH - 96, draw, 2):
        draw.text((48, y), line, font=font, fill=FOREGROUND)
        y += 36
    draw.text(
        (48, 160),
        f"{labels['observed']}  {model.observed_on.isoformat()}",
        font=small,
        fill=MUTED,
    )
    draw.text(
        (48, 202),
        f"{labels['coverage']}  {model.overall_coverage.value}",
        font=small,
        fill=FOREGROUND,
    )
    draw.line((48, 244, WIDTH - 48, 244), fill=(51, 65, 85), width=2)
    declared = f"{model.declaration_authority.value}/{model.declaration_coverage.value}"
    draw.text((48, 270), f"{labels['declared']}  {declared}", font=small, fill=ACCENT)
    draw.text(
        (48, 310),
        f"{labels['events']}  {model.uncovered_events}",
        font=small,
        fill=FOREGROUND,
    )
    draw.text((48, 350), f"{labels['leaks']}  {model.leaks}", font=small, fill=FOREGROUND)
    stages = ", ".join(
        f"{stage.name}:{stage.status.value}" for stage in model.stages if stage.applicable
    )
    for index, line in enumerate(_lines(stages or labels["no_stages"], small, WIDTH - 96, draw, 2)):
        draw.text((48, 408 + index * 24), line, font=small, fill=MUTED)
    kinds: dict[str, int] = {}
    for finding in model.findings:
        key = finding.kind or "OTHER"
        kinds[key] = kinds.get(key, 0) + 1
    if kinds:
        summary = f"{labels['findings']}  " + ", ".join(
            f"{key}:{kinds[key]}" for key in sorted(kinds)
        )
        draw.text((48, 468), summary, font=small, fill=MUTED)
    output = BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


class PNGReporter:
    name = "png"

    def render(self, model: EvidenceCardModel) -> bytes:
        return render_png(model)


__all__ = ["BACKGROUND", "FOREGROUND", "HEIGHT", "WIDTH", "PNGReporter", "render_png"]
