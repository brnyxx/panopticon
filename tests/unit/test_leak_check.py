from pathlib import Path

import pytest

from panopticon.util.leak_check import (
    LeakContext,
    LeakError,
    assert_clean,
    find_leaks,
    redact_token,
)

LEAK_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "leak"


@pytest.mark.parametrize("payload", sorted(LEAK_DIR.glob("*.txt")), ids=lambda p: p.name)
def test_every_leak_fixture_is_rejected(payload: Path) -> None:
    with pytest.raises(LeakError):
        assert_clean(
            payload.read_text(),
            LeakContext(
                home_paths=("/home/alice",),
                secrets=("REAL-SECRET-VALUE", "REAL/SECRET+VALUE=="),
            ),
        )


def test_clean_text_passes() -> None:
    assert find_leaks("READ ~/.ssh/config\nNET api.github.com:443") == ()


def test_redact() -> None:
    assert redact_token("ghp_abcdefghijklmnopqrstuvwxyz1234") == "ghp_…234"
