"""Build deterministic local brand images from the shipped Panopticon contracts."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from panopticon.badge.font import DEFAULT_FONT
from panopticon.badge.model import CardFinding, CardStage, DeclarationAuthority, EvidenceCardModel
from panopticon.models.state import StageStatus
from panopticon.reporters.png import render_png

ROOT = Path(__file__).resolve().parents[1]
SITE_ASSETS = ROOT / "site" / "assets"
GITHUB_ASSETS = ROOT / ".github" / "assets"

BG = "#010714"
SURFACE = "#071022"
KEYLINE = "#1d2b43"
KEYLINE_STRONG = "#40536e"
RING = "#42587b"
RING_SOFT = "#6b7eb0"
TINT = "#7189cd"
ACCENT = "#fb7c05"
SIGNAL = "#f5b52b"
OBSERVED = "#67b376"
TEXT = "#f2f0ed"
TEXT_2 = "#afb5c9"
TEXT_3 = "#747e94"


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(DEFAULT_FONT), size)


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def render_logo_png(size: int = 32) -> bytes:
    """Render the small, filter-free aperture mark with supersampling."""
    scale = 8
    canvas = Image.new("RGB", (size * scale, size * scale), BG)
    draw = ImageDraw.Draw(canvas)
    unit = size * scale / 256

    def box(inset: float) -> tuple[int, int, int, int]:
        value = round(inset * unit)
        edge = size * scale - value - 1
        return value, value, edge, edge

    radius = round(56 * unit)
    draw.rounded_rectangle((0, 0, size * scale - 1, size * scale - 1), radius=radius, fill=BG)
    draw.ellipse(box(34), outline=RING, width=max(1, round(16 * unit)))
    draw.arc(
        box(34),
        start=308,
        end=343,
        fill=ACCENT,
        width=max(1, round(18 * unit)),
    )
    draw.ellipse(box(78), fill=SURFACE, outline=TEXT, width=max(1, round(16 * unit)))
    draw.rounded_rectangle(
        (
            round(108 * unit),
            round(98 * unit),
            round(148 * unit),
            round(158 * unit),
        ),
        radius=max(1, round(3 * unit)),
        fill=ACCENT,
    )
    resized = canvas.resize((size, size), Image.Resampling.LANCZOS)
    return _png(resized)


def render_social_card() -> bytes:
    """Render the local Open Graph card as an evidence-led product frame."""
    image = Image.new("RGB", (1200, 630), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 1179, 609), outline=KEYLINE, width=1)
    draw.line((20, 104, 1179, 104), fill=KEYLINE, width=1)
    logo = Image.open(BytesIO(render_logo_png(64))).convert("RGB")
    image.paste(logo, (48, 32))

    mono = _font(18)
    small = _font(15)
    title = _font(52)
    body = _font(21)
    draw.text((130, 42), "PANOPTICON", fill=TEXT, font=mono, stroke_width=0)
    draw.text((130, 72), "We don't watch you. We watch your MCPs.", fill=TEXT_2, font=small)
    draw.text((48, 140), "One MCP call becomes", fill=TEXT, font=title)
    draw.text((48, 201), "an inspectable record.", fill=TEXT, font=title)
    draw.text(
        (50, 278),
        "Selected target  /  generated decoys  /  explicit evidence",
        fill=TEXT_2,
        font=body,
    )

    panel = (694, 138, 1136, 520)
    draw.rectangle(panel, fill=SURFACE, outline=KEYLINE_STRONG, width=1)
    draw.line((716, 202, 1114, 202), fill=KEYLINE, width=1)
    draw.text((716, 166), "ILLUSTRATIVE EVIDENCE", fill=TINT, font=small)
    rows = (
        ("FILES", "COMPLETE", OBSERVED, "circle"),
        ("NETWORK", "COMPLETE", OBSERVED, "circle"),
        ("PROCESSES", "UNSUPPORTED", SIGNAL, "triangle"),
        ("SNAPSHOT", "INCOMPLETE", ACCENT, "square"),
    )
    row_font = _font(16)
    for index, (label, status, color, shape) in enumerate(rows):
        top = 224 + index * 56
        draw.text((716, top), label, fill=TEXT_2, font=row_font)
        x, y = 915, top + 9
        if shape == "circle":
            draw.ellipse((x, y, x + 12, y + 12), outline=color, width=2)
        elif shape == "triangle":
            draw.polygon(((x + 6, y), (x + 12, y + 12), (x, y + 12)), fill=color)
        else:
            draw.rectangle((x, y, x + 12, y + 12), outline=color, width=2)
        draw.text((940, top), status, fill=color, font=row_font)
        draw.line((716, top + 38, 1114, top + 38), fill=KEYLINE, width=1)
    draw.rectangle((716, 466, 1114, 500), fill=BG, outline=SIGNAL, width=1)
    draw.text((730, 474), "WATCH-001 / DECOY MARKER MATCH", fill=SIGNAL, font=small)
    draw.text((48, 560), "LOCAL / EXPLICIT / REVERSIBLE", fill=TINT, font=small)
    draw.text((1152, 560), "NOT OBSERVED IS NOT A PASS.", anchor="ra", fill=SIGNAL, font=small)
    return _png(image)


def render_fixture_evidence() -> bytes:
    """Render an authentic reporter artifact from a sanitized fixed fixture."""
    model = EvidenceCardModel(
        server="illustrative-fixture-mcp",
        observed_on=date(2026, 8, 31),
        overall_coverage=StageStatus.INCOMPLETE,
        declaration_authority=DeclarationAuthority.AUTHORITATIVE,
        declaration_coverage=StageStatus.COMPLETE,
        stages=(
            CardStage("FILES", StageStatus.COMPLETE),
            CardStage("NET", StageStatus.COMPLETE),
            CardStage("PROC", StageStatus.UNSUPPORTED),
            CardStage("SNAP", StageStatus.INCOMPLETE),
        ),
        leaks=1,
        findings=(CardFinding("WATCH-001", kind="behavior"),),
        locale="en",
    )
    return render_png(model, font_path=str(DEFAULT_FONT))


def build() -> None:
    SITE_ASSETS.mkdir(parents=True, exist_ok=True)
    GITHUB_ASSETS.mkdir(parents=True, exist_ok=True)
    (SITE_ASSETS / "logo-32.png").write_bytes(render_logo_png())
    (SITE_ASSETS / "social-card.png").write_bytes(render_social_card())
    (GITHUB_ASSETS / "evidence-card.png").write_bytes(render_fixture_evidence())


if __name__ == "__main__":
    build()
