"""Deterministic bilingual site-builder contract tests."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import build_site as site_builder
from build_site import SiteBuildError, build, load_content

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_build_emits_identical_bilingual_routes_and_assets(tmp_path: Path) -> None:
    output = tmp_path / "public"

    build(output)
    first = _snapshot(output)
    build(output)

    assert _snapshot(output) == first
    assert set(first) == {
        "assets/logo-32.png",
        "assets/logo.svg",
        "assets/social-card.png",
        "assets/site.css",
        "assets/site.js",
        "index.html",
        "ko/index.html",
    }
    assert b'<html lang="en">' in first["index.html"]
    assert b'<html lang="ko">' in first["ko/index.html"]
    assert b'href="assets/site.css"' in first["index.html"]
    assert b'href="../assets/site.css"' in first["ko/index.html"]


def test_locale_key_drift_is_rejected(tmp_path: Path) -> None:
    content = tmp_path / "content"
    shutil.copytree(SITE / "content", content)
    korean = json.loads((content / "ko.json").read_text(encoding="utf-8"))
    korean.pop("hero_title")
    (content / "ko.json").write_text(json.dumps(korean), encoding="utf-8")

    with pytest.raises(SiteBuildError, match="LOCALE_KEY_MISMATCH"):
        load_content(content)


def test_locale_text_is_escaped_in_text_and_attributes(tmp_path: Path) -> None:
    source = tmp_path / "site"
    shutil.copytree(SITE, source)
    english = json.loads((source / "content" / "en.json").read_text(encoding="utf-8"))
    english["title"] = '"><script data-injected="true">'
    english["hero_title"] = "<em>injected</em>"
    (source / "content" / "en.json").write_text(
        json.dumps(english, ensure_ascii=False), encoding="utf-8"
    )

    output = tmp_path / "public"
    build(output, source=source)
    document = (output / "index.html").read_text(encoding="utf-8")

    assert '<script data-injected="true">' not in document
    assert "<em>injected</em>" not in document
    assert "&lt;em&gt;injected&lt;/em&gt;" in document
    assert "&quot;&gt;&lt;script" in document


def test_failed_build_preserves_previous_output(tmp_path: Path) -> None:
    source = tmp_path / "site"
    shutil.copytree(SITE, source)
    output = tmp_path / "public"
    build(output, source=source)
    before = _snapshot(output)
    (source / "assets" / "site.js").unlink()

    with pytest.raises(SiteBuildError, match=r"MISSING_ASSET:site\.js"):
        build(output, source=source)

    assert _snapshot(output) == before


def test_source_and_output_paths_must_not_overlap(tmp_path: Path) -> None:
    source = tmp_path / "site"
    shutil.copytree(SITE, source)

    for output in (source, tmp_path, source / "public"):
        with pytest.raises(SiteBuildError, match="SOURCE_OUTPUT_OVERLAP"):
            build(output, source=source)


def test_failed_atomic_exchange_keeps_previous_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "site"
    shutil.copytree(SITE, source)
    output = tmp_path / "public"
    build(output, source=source)
    before = _snapshot(output)
    english = json.loads((source / "content/en.json").read_text(encoding="utf-8"))
    english["hero_title"] = "A changed build that must not be published."
    (source / "content/en.json").write_text(
        json.dumps(english, ensure_ascii=False), encoding="utf-8"
    )

    def fail_exchange(_staging: Path, _destination: Path) -> None:
        raise OSError("injected exchange failure")

    monkeypatch.setattr(site_builder, "_exchange_directories", fail_exchange)
    with pytest.raises(OSError, match="injected exchange failure"):
        build(output, source=source)

    assert _snapshot(output) == before
