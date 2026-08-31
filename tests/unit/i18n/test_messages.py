from panopticon import __version__
from panopticon.i18n.messages import (
    EN_MESSAGES,
    KO_MESSAGES,
    MESSAGE_KEYS,
    epilog,
    get_message,
    select_locale,
)


def test_catalog_keys_have_exact_parity() -> None:
    assert set(EN_MESSAGES) == set(KO_MESSAGES) == set(MESSAGE_KEYS)


def test_locale_precedence_and_unknown_fallback() -> None:
    assert select_locale(environ={"PANO_LANG": "ko", "LC_ALL": "en"}) == "ko"
    assert select_locale(environ={"LC_ALL": "ko", "LANG": "en"}) == "ko"
    assert select_locale("en", {"PANO_LANG": "ko"}) == "en"
    assert select_locale("fr", {"PANO_LANG": "ko"}) == "en"
    assert get_message("doctor", locale="ko").startswith("1. 설정")


def test_epilog_orders_first_use_commands() -> None:
    lines = epilog(locale="en").splitlines()
    assert lines[:3] == [
        "1. Check your setup: pano doctor --offline",
        "2. Observe one server: pano watch SERVER_NAME --offline",
        "3. Explain a rule in Korean: pano explain RULE_ID --lang ko",
    ]
    assert lines[3] == f"Install: uv tool install panopticon-mcp=={__version__}"
