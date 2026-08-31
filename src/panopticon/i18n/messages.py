"""Typed bilingual messages for novice-facing CLI guidance."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, TypedDict, cast

from panopticon import __version__
from panopticon.i18n.loader import locale_precedence

Locale = Literal["en", "ko"]
MessageKey = Literal[
    "install",
    "doctor",
    "watch",
    "explain",
    "example_tool",
    "coverage_complete",
    "coverage_unsupported",
    "coverage_incomplete",
    "next_command",
]


class MessageCatalog(TypedDict):
    install: str
    doctor: str
    watch: str
    explain: str
    example_tool: str
    coverage_complete: str
    coverage_unsupported: str
    coverage_incomplete: str
    next_command: str


MESSAGES: Mapping[Locale, MessageCatalog] = {
    "en": {
        "install": f"Install: uv tool install panopticon-mcp=={__version__}",
        "doctor": "1. Check your setup: pano doctor --offline",
        "watch": "2. Observe one server: pano watch SERVER_NAME --offline",
        "explain": "3. Explain a rule in Korean: pano explain RULE_ID --lang ko",
        "example_tool": "Example tool: file_read",
        "coverage_complete": "file/net: COMPLETE/COMPLETED",
        "coverage_unsupported": "process: UNSUPPORTED/RUNTIME_UNAVAILABLE",
        "coverage_incomplete": "snapshot: INCOMPLETE/TIMEOUT",
        "next_command": "Next: pano watch SERVER_NAME --offline",
    },
    "ko": {
        "install": f"설치: uv tool install panopticon-mcp=={__version__}",
        "doctor": "1. 설정 확인: pano doctor --offline",
        "watch": "2. 서버 하나 관찰: pano watch SERVER_NAME --offline",
        "explain": "3. 규칙 설명(한국어): pano explain RULE_ID --lang ko",
        "example_tool": "도구 예시: file_read",
        "coverage_complete": "file/net: COMPLETE/COMPLETED",
        "coverage_unsupported": "process: UNSUPPORTED/RUNTIME_UNAVAILABLE",
        "coverage_incomplete": "snapshot: INCOMPLETE/TIMEOUT",
        "next_command": "다음: pano watch SERVER_NAME --offline",
    },
}

EN_MESSAGES = MESSAGES["en"]
KO_MESSAGES = MESSAGES["ko"]
MESSAGE_KEYS = frozenset(MESSAGES["en"])


def select_locale(explicit: str | None = None, environ: Mapping[str, str] | None = None) -> Locale:
    """Select the first supported locale using the shared precedence rules."""
    selected = locale_precedence(explicit, environ)
    return "ko" if selected and selected[0] == "ko" else "en"


def message(
    key: str,
    *,
    locale: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Look up a message, falling back to English for unknown locales or keys."""
    selected: Locale = select_locale(locale, environ)
    if key not in MESSAGE_KEYS:
        return key
    return MESSAGES[selected][cast(MessageKey, key)]


get_message = message
resolve_locale = select_locale


def epilog(*, locale: str | None = None, environ: Mapping[str, str] | None = None) -> str:
    selected = select_locale(locale, environ)
    catalog = MESSAGES[selected]
    keys: tuple[MessageKey, ...] = (
        "doctor",
        "watch",
        "explain",
        "install",
        "example_tool",
        "coverage_complete",
        "coverage_unsupported",
        "coverage_incomplete",
    )
    return "\n".join(catalog[key] for key in keys)


__all__ = [
    "EN_MESSAGES",
    "KO_MESSAGES",
    "MESSAGES",
    "MESSAGE_KEYS",
    "Locale",
    "MessageCatalog",
    "epilog",
    "get_message",
    "message",
    "resolve_locale",
    "select_locale",
]
