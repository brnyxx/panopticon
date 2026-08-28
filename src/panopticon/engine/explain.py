"""Typed explanation service for bilingual rule documents."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from panopticon.i18n.catalog import BY_ID
from panopticon.i18n.loader import (
    InvalidDocumentError,
    MissingDocumentError,
    RuleDocument,
    load_document,
)


class ExplainStatus(StrEnum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class ExplainResult:
    rule_id: str
    status: ExplainStatus
    document: RuleDocument | None = None
    reason_code: str = "COMPLETED"


def explain_rule(
    rule_id: str,
    *,
    locale: str | None = None,
    root: Path | str | None = None,
) -> ExplainResult:
    normalized_id = rule_id.upper()
    if normalized_id not in BY_ID:
        return ExplainResult(
            normalized_id,
            ExplainStatus.UNKNOWN,
            reason_code="UNKNOWN_RULE_ID",
        )
    try:
        document = load_document(normalized_id, locale=locale, root=root)
    except MissingDocumentError:
        return ExplainResult(
            normalized_id,
            ExplainStatus.INCOMPLETE,
            reason_code="MISSING_RULE_DOCUMENT",
        )
    except InvalidDocumentError:
        return ExplainResult(
            normalized_id,
            ExplainStatus.INCOMPLETE,
            reason_code="INVALID_RULE_DOCUMENT",
        )
    return ExplainResult(normalized_id, ExplainStatus.KNOWN, document=document)


__all__ = ["ExplainResult", "ExplainStatus", "explain_rule"]
