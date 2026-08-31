"""Repository and Pages brand assets remain deterministic and contract-aligned."""

from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path
from types import ModuleType

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "build_brand_assets", ROOT / "scripts/build_brand_assets.py"
)
assert SPEC is not None and SPEC.loader is not None
build_brand_assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_brand_assets)
assert isinstance(build_brand_assets, ModuleType)


def _image(payload: bytes, expected_size: tuple[int, int]) -> None:
    with Image.open(BytesIO(payload)) as image:
        assert image.size == expected_size
        assert image.mode == "RGB"
        assert image.info == {}


def test_generated_and_checked_brand_images_have_stable_contracts() -> None:
    logo = build_brand_assets.render_logo_png()
    social = build_brand_assets.render_social_card()
    evidence = build_brand_assets.render_fixture_evidence()

    assert logo == build_brand_assets.render_logo_png()
    assert social == build_brand_assets.render_social_card()
    assert evidence == build_brand_assets.render_fixture_evidence()
    _image(logo, (32, 32))
    _image(social, (1200, 630))
    _image(evidence, (960, 540))
    _image((ROOT / "site/assets/logo-32.png").read_bytes(), (32, 32))
    _image((ROOT / "site/assets/social-card.png").read_bytes(), (1200, 630))
    _image((ROOT / ".github/assets/evidence-card.png").read_bytes(), (960, 540))


def test_logo_sources_are_one_filter_free_mark() -> None:
    repository_logo = (ROOT / ".github/assets/logo.svg").read_text(encoding="utf-8")
    site_logo = (ROOT / "site/assets/logo.svg").read_text(encoding="utf-8")

    assert repository_logo == site_logo
    assert "filter" not in repository_logo
    assert repository_logo.count("#FB7C05") == 2
    assert 'stroke="#F2F0ED" stroke-width="16"' in repository_logo
    assert "stroke-dasharray" in repository_logo
    assert "aria-labelledby" in repository_logo


def test_repository_hero_is_a_product_flow_not_scene_art() -> None:
    hero = (ROOT / ".github/assets/hero.svg").read_text(encoding="utf-8")
    lowered = hero.casefold()

    for phrase in (
        "select target",
        "decoy runtime",
        "evidence record",
        "watch-001",
        "illustrative fixture",
        "not observed is not a pass",
    ):
        assert phrase in lowered
    for forbidden in ("prison", "cell", "watchtower", "robot", "filter"):
        assert forbidden not in lowered
    for legacy_token in ("#FF7A1A", "#FFB020", "#0A0E1A"):
        assert legacy_token not in hero
