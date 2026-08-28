"""Load and parse exact bilingual rule explanation documents."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

SECTION_IDS = (
    "Problem",
    "Impact",
    "Evidence",
    "Recommended action",
    "How to verify",
    "Limits",
)
_KO_SECTION_IDS = ("문제", "영향", "근거", "권장 조치", "확인 방법", "제한")
_KO_SECTION_MAP = dict(zip(_KO_SECTION_IDS, SECTION_IDS, strict=True))
_HEADING = re.compile(r"^##\s+(.+?)\s*$")
_RULE_ID = re.compile(r"^(CFG|HIST|WATCH|FIX|SENT)-\d{3}$")


@dataclass(frozen=True, slots=True)
class RuleSection:
    section_id: str
    body: str


@dataclass(frozen=True, slots=True)
class RuleDocument:
    rule_id: str
    locale: str
    sections: tuple[RuleSection, ...]

    def section(self, section_id: str) -> str:
        for section in self.sections:
            if section.section_id == section_id:
                return section.body
        raise KeyError(section_id)


class MissingDocumentError(FileNotFoundError):
    pass


class InvalidDocumentError(ValueError):
    pass


def normalize_locale(value: str | None) -> str:
    normalized = re.sub(r"_", "-", (value or "").strip().casefold())
    return "ko" if normalized.startswith("ko") else "en"


def locale_precedence(
    explicit: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    active = os.environ if environ is None else environ
    candidates = (
        explicit,
        active.get("LC_ALL"),
        active.get("LC_MESSAGES"),
        active.get("LANG"),
        "en",
    )
    result: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        locale = normalize_locale(candidate)
        if locale not in result:
            result.append(locale)
    return tuple(result)


def parse_document(text: str, rule_id: str, locale: str) -> RuleDocument:
    bodies: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = _HEADING.fullmatch(line)
        if match:
            heading = match.group(1)
            if normalize_locale(locale) == "ko":
                heading = _KO_SECTION_MAP.get(heading, heading)
            if heading not in SECTION_IDS:
                current = None
                continue
            if heading in bodies:
                raise InvalidDocumentError(f"DUPLICATE_SECTION:{heading}")
            current = heading
            bodies[heading] = []
            continue
        if current is not None:
            bodies[current].append(line)
    if tuple(bodies) != SECTION_IDS:
        raise InvalidDocumentError("INVALID_SECTION_SET")
    sections = tuple(
        RuleSection(section_id, "\n".join(bodies[section_id]).strip()) for section_id in SECTION_IDS
    )
    if any(not section.body for section in sections):
        raise InvalidDocumentError("EMPTY_SECTION")
    return RuleDocument(rule_id, normalize_locale(locale), sections)


def load_document(
    rule_id: str,
    *,
    locale: str | None = None,
    root: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
) -> RuleDocument:
    normalized_id = rule_id.upper()
    if _RULE_ID.fullmatch(normalized_id) is None:
        raise MissingDocumentError("UNKNOWN_RULE_ID")
    base = Path(root) if root is not None else Path(__file__).parent
    for selected_locale in locale_precedence(locale, environ):
        path = base / selected_locale / "rules" / f"{normalized_id}.md"
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        return parse_document(text, normalized_id, selected_locale)
    raise MissingDocumentError("MISSING_RULE_DOCUMENT")


__all__ = [
    "SECTION_IDS",
    "InvalidDocumentError",
    "MissingDocumentError",
    "RuleDocument",
    "RuleSection",
    "load_document",
    "locale_precedence",
    "normalize_locale",
    "parse_document",
]
