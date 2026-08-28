from __future__ import annotations

import pytest

from panopticon.release import render_formula


def _hashes() -> dict[str, str]:
    return {
        f"panopticon-1.0.0-{target}.tar.gz": character * 64
        for target, character in (
            ("darwin-arm64", "a"),
            ("darwin-x86_64", "b"),
            ("linux-arm64", "c"),
            ("linux-x86_64", "d"),
        )
    }


def test_formula_selects_every_supported_archive_by_os_and_architecture() -> None:
    formula = render_formula(
        _hashes(),
        "https://github.com/brnyxx/panopticon/releases/download/v1.0.0/",
    )

    assert formula.count("  on_macos do") == 1
    assert formula.count("  on_linux do") == 1
    assert formula.count("      sha256 ") == 4
    assert "Hardware::CPU.arm?" in formula
    assert formula.count("    else") == 2
    assert 'bin.install "pano"' in formula
    assert "pano 1.0.0 (schema 1.0)" in formula


def test_formula_rejects_nonrelease_url_and_missing_digest() -> None:
    with pytest.raises(ValueError, match="INVALID_HOMEBREW_RELEASE_URL"):
        render_formula(_hashes(), "https://example.test/")
    with pytest.raises(ValueError, match="INVALID_HOMEBREW_DIGEST"):
        render_formula(
            {},
            "https://github.com/brnyxx/panopticon/releases/download/v1.0.0/",
        )
