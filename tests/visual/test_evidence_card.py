from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree

import pytest
from PIL import Image, ImageChops

from panopticon.badge.eligibility import badge_eligible
from panopticon.badge.font import DEFAULT_FONT
from panopticon.badge.model import CardFinding, CardStage, DeclarationAuthority, EvidenceCardModel
from panopticon.badge.svg import BadgeIneligibleError, render_svg
from panopticon.models.state import StageStatus
from panopticon.reporters.png import (
    ACCENT,
    BACKGROUND,
    FOREGROUND,
    HEIGHT,
    MUTED,
    WIDTH,
    render_png,
)
from panopticon.reporters.visual import VisualFormat, persist_visual
from panopticon.store.contracts import PersistRejected, PersistSuccess
from panopticon.store.repository import ArtifactRepository

OBSERVED_ON = date(2026, 1, 30)
GOLDEN_HASHES = {
    "en": (
        "0a72d7f2eae00bd439ecce18db7ee4b0ebe5db956cd9d01f070cdce8a69a39fd",
        "f00daac7ec085a0880ce329e0c3c90bde7fd8ec3a8bf1b08e608669ac44f50a5",
    ),
    "ko": (
        "58a8c52c66e37b17cf4e03c3a6163ef5b9047e4ba4b1658c38bc150f03197c90",
        "cc0026589c0aaea87ef6ff5870c915c62768acbc781e4b8d638d21a9e29e691d",
    ),
}


def _model(
    *,
    locale: Literal["en", "ko"] = "en",
    server: str = "omo-evidence",
) -> EvidenceCardModel:
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
        locale=locale,
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


def _luminance(color: tuple[int, int, int]) -> float:
    channels = tuple(
        channel / 255 / 12.92
        if channel / 255 <= 0.04045
        else ((channel / 255 + 0.055) / 1.055) ** 2.4
        for channel in color
    )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_ko_en_cards_and_eligible_badge(tmp_path: Path) -> None:
    """OMO-30: English/Korean cards and badge output are deterministic and accessible."""
    assert DEFAULT_FONT.exists()
    for locale in ("en", "ko"):
        model = _model(locale=locale)
        first = render_png(model, font_path=str(DEFAULT_FONT))
        second = render_png(model, font_path=str(DEFAULT_FONT))
        assert first == second
        assert hashlib.sha256(first).hexdigest() == GOLDEN_HASHES[locale][0]
        _assert_png_contract(first)
        with Image.open(BytesIO(first)) as image:
            # Stable heading pixels prove that the bundled font rendered text.
            heading = image.crop((40, 25, 500, 75))
            heading_bg = Image.new("RGB", heading.size, BACKGROUND)
            assert ImageChops.difference(heading, heading_bg).getbbox() is not None
        svg = render_svg(model)
        assert hashlib.sha256(svg.encode()).hexdigest() == GOLDEN_HASHES[locale][1]
        _assert_svg_accessibility(svg)
        assert OBSERVED_ON.isoformat() in svg
        assert badge_eligible(model)
        repository = ArtifactRepository(tmp_path / locale)
        png_result = persist_visual(
            repository,
            tmp_path / locale / "evidence.png",
            model,
            VisualFormat.PNG,
        )
        svg_result = persist_visual(
            repository,
            tmp_path / locale / "badge.svg",
            model,
            VisualFormat.SVG,
        )
        assert isinstance(png_result, PersistSuccess)
        assert isinstance(svg_result, PersistSuccess)
        assert png_result.target.read_bytes() == first
        assert svg_result.target.read_text() == svg
    assert all(_contrast(color, BACKGROUND) >= 4.5 for color in (FOREGROUND, ACCENT, MUTED))
    rejected = persist_visual(
        ArtifactRepository(tmp_path / "rejected"),
        tmp_path / "rejected" / "evidence.png",
        _model(server="ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"),
        VisualFormat.PNG,
    )
    assert isinstance(rejected, PersistRejected)
    assert not rejected.target.exists()


def test_long_cjk_partial_observation_is_legible_and_ineligible(tmp_path: Path) -> None:
    """OMO-30: long CJK text remains bounded while every incomplete prerequisite denies a badge."""
    model = _model(locale="ko", server="매우 긴 관찰 대상 서버 이름과 한글 혼합" * 12)
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
