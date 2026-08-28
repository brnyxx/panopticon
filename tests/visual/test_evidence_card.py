from __future__ import annotations

from dataclasses import replace
from datetime import date
from io import BytesIO
from xml.etree import ElementTree

import pytest
from PIL import Image, ImageChops

from panopticon.badge.eligibility import badge_eligible
from panopticon.badge.font import DEFAULT_FONT
from panopticon.badge.model import CardFinding, CardStage, DeclarationAuthority, EvidenceCardModel
from panopticon.badge.svg import BadgeIneligibleError, render_svg
from panopticon.models.state import StageStatus
from panopticon.reporters.png import BACKGROUND, HEIGHT, WIDTH, render_png

OBSERVED_ON = date(2026, 1, 30)


def _model(*, locale: str = "en", server: str = "omo-evidence") -> EvidenceCardModel:
    return EvidenceCardModel(
        server=server,
        observed_on=OBSERVED_ON,
        overall_coverage=StageStatus.COMPLETE,
        declaration_authority=DeclarationAuthority.AUTHORITATIVE,
        declaration_coverage=StageStatus.COMPLETE,
        stages=(
            CardStage("MCP", StageStatus.COMPLETE),
            CardStage("OBSERVE", StageStatus.COMPLETE),
        ),
        locale=locale,  # type: ignore[arg-type]
    )


def _assert_png_contract(payload: bytes) -> None:
    with Image.open(BytesIO(payload)) as image:
        assert image.size == (WIDTH, HEIGHT)
        assert image.info == {}
        assert image.mode == "RGB"
        background = Image.new("RGB", image.size, BACKGROUND)
        diff = ImageChops.difference(image, background)
        assert diff.getbbox() is not None
        extrema = diff.getextrema()
        assert any(high > low for low, high in extrema)
        # Ink must occupy the text area, not merely the decorative top stripe.
        crop = image.crop((40, 30, WIDTH - 40, 510))
        crop_bg = Image.new("RGB", crop.size, BACKGROUND)
        assert ImageChops.difference(crop, crop_bg).getbbox() is not None


def _assert_svg_accessibility(svg: str) -> None:
    root = ElementTree.fromstring(svg)
    assert root.tag.rsplit("}", 1)[-1] == "svg"
    assert root.attrib["role"] == "img"
    assert root.attrib["aria-labelledby"] == "title desc"
    title = root.find("{http://www.w3.org/2000/svg}title")
    desc = root.find("{http://www.w3.org/2000/svg}desc")
    assert title is not None and title.text
    assert desc is not None and desc.text


def test_ko_en_cards_and_eligible_badge(tmp_path) -> None:
    """OMO-30: English/Korean cards and badge output are deterministic and accessible."""
    assert DEFAULT_FONT.exists()
    for locale in ("en", "ko"):
        model = _model(locale=locale)
        first = render_png(model, font_path=str(DEFAULT_FONT))
        second = render_png(model, font_path=str(DEFAULT_FONT))
        assert first == second
        _assert_png_contract(first)
        with Image.open(BytesIO(first)) as image:
            # Stable heading pixels prove that the bundled font rendered text.
            heading = image.crop((40, 25, 500, 75))
            heading_bg = Image.new("RGB", heading.size, BACKGROUND)
            assert ImageChops.difference(heading, heading_bg).getbbox() is not None
        svg = render_svg(model)
        _assert_svg_accessibility(svg)
        assert OBSERVED_ON.isoformat() in svg
        assert badge_eligible(model)
        assert "DECLARED = OBSERVED" in svg or "선언 = 관찰" in svg
        (tmp_path / f"{locale}.png").write_bytes(first)
        (tmp_path / f"{locale}.svg").write_text(svg, encoding="utf-8")


def test_long_cjk_partial_observation_is_legible_and_ineligible(tmp_path) -> None:
    """OMO-30: long CJK text remains bounded while every incomplete prerequisite denies a badge."""
    model = _model(locale="ko", server="非常に長い観察対象サーバー名과日本語混在" * 12)
    payload = render_png(model, font_path=str(DEFAULT_FONT))
    assert payload == render_png(model, font_path=str(DEFAULT_FONT))
    _assert_png_contract(payload)
    with Image.open(BytesIO(payload)) as image:
        # Wrapped CJK text is visible in the reserved server region and does not overflow it.
        region = image.crop((40, 70, WIDTH - 40, 150))
        region_bg = Image.new("RGB", region.size, BACKGROUND)
        ink = ImageChops.difference(region, region_bg).getbbox()
        assert ink is not None
        assert ink[2] <= region.width - 1
    (tmp_path / "long-cjk.png").write_bytes(payload)

    denied = (
        replace(model, declaration_authority=DeclarationAuthority.PARTIAL),
        replace(model, declaration_coverage=StageStatus.PARTIAL),
        replace(model, overall_coverage=StageStatus.PARTIAL),
        replace(model, stages=(CardStage("MCP", StageStatus.PARTIAL),)),
        replace(
            model, findings=(CardFinding("OMO-SUPPRESSED", kind="suppressed", suppressed=True),)
        ),
        replace(model, leaks=1),
        replace(model, excluded_evidence=1),
        replace(model, uncovered_events=1),
    )
    for candidate in denied:
        assert not badge_eligible(candidate)
        with pytest.raises(BadgeIneligibleError, match="BADGE_INELIGIBLE"):
            render_svg(candidate)
