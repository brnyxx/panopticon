from __future__ import annotations

import pytest

from panopticon.release import render_formula

VERSION = "1.0.1"
BASE_URL = f"https://github.com/brnyxx/panopticon/releases/download/v{VERSION}/"


def _hashes() -> dict[str, str]:
    return {
        f"panopticon-{VERSION}-{target}.tar.gz": character * 64
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
        BASE_URL,
        VERSION,
    )

    assert formula.count("  on_macos do") == 1
    assert formula.count("  on_linux do") == 1
    assert formula.count("      sha256 ") == 4
    assert "Hardware::CPU.arm?" in formula
    assert formula.count("    else") == 2
    assert 'bin.install "pano"' in formula
    assert f"releases/download/v{VERSION}/panopticon-{VERSION}-linux-arm64.tar.gz" in formula
    assert f"pano {VERSION} (schema 1.0)" in formula


def test_formula_rejects_nonrelease_url_and_missing_digest() -> None:
    with pytest.raises(ValueError, match="INVALID_HOMEBREW_RELEASE_URL"):
        render_formula(_hashes(), "https://example.test/", VERSION)
    with pytest.raises(ValueError, match="INVALID_HOMEBREW_DIGEST"):
        render_formula(
            {},
            BASE_URL,
            VERSION,
        )


@pytest.mark.parametrize("version", ("1.0", "v1.0.1", "1.0.1rc1", "01.0.1"))
def test_formula_rejects_invalid_stable_version(version: str) -> None:
    with pytest.raises(ValueError, match="INVALID_RELEASE_VERSION"):
        render_formula(_hashes(), BASE_URL, version)
