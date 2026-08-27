"""Typed non-vacuous rule and bilingual i18n scope checking."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique


@unique
class ScopeIssueCode(StrEnum):
    UNSTAGED_SCOPE = "UNSTAGED_SCOPE"
    UNSTAGED_EMPTY_SCOPE = "UNSTAGED_EMPTY_SCOPE"
    DUPLICATE_EXPECTED_ID = "DUPLICATE_EXPECTED_ID"
    DUPLICATE_RESERVED_ID = "DUPLICATE_RESERVED_ID"
    EXPECTED_RESERVED_OVERLAP = "EXPECTED_RESERVED_OVERLAP"
    MISSING_REGISTERED_ID = "MISSING_REGISTERED_ID"
    MISSING_KO_ID = "MISSING_KO_ID"
    MISSING_EN_ID = "MISSING_EN_ID"
    MISSING_RESERVED_KO_ID = "MISSING_RESERVED_KO_ID"
    MISSING_RESERVED_EN_ID = "MISSING_RESERVED_EN_ID"
    MISSING_POSITIVE_FIXTURE = "MISSING_POSITIVE_FIXTURE"
    MISSING_NEGATIVE_FIXTURE = "MISSING_NEGATIVE_FIXTURE"
    I18N_PARITY = "I18N_PARITY"
    UNEXPECTED_REGISTERED_ID = "UNEXPECTED_REGISTERED_ID"
    UNEXPECTED_KO_ID = "UNEXPECTED_KO_ID"
    UNEXPECTED_EN_ID = "UNEXPECTED_EN_ID"
    UNEXPECTED_POSITIVE_FIXTURE = "UNEXPECTED_POSITIVE_FIXTURE"
    UNEXPECTED_NEGATIVE_FIXTURE = "UNEXPECTED_NEGATIVE_FIXTURE"
    MISSING_SCOPE_MANIFEST = "MISSING_SCOPE_MANIFEST"
    INVALID_SCOPE_MANIFEST = "INVALID_SCOPE_MANIFEST"
    MANIFEST_SCOPE_MISMATCH = "MANIFEST_SCOPE_MISMATCH"


@dataclass(frozen=True, slots=True)
class RuleScopeManifest:
    staged: bool
    expected_ids: tuple[str, ...]
    reserved_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RuleScopeInventory:
    registered_ids: tuple[str, ...]
    ko_ids: tuple[str, ...]
    en_ids: tuple[str, ...]
    positive_fixture_ids: tuple[str, ...]
    negative_fixture_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScopeIssue:
    code: ScopeIssueCode
    subject: str | None = None


def _missing(
    expected_ids: tuple[str, ...], observed_ids: tuple[str, ...], code: ScopeIssueCode
) -> tuple[ScopeIssue, ...]:
    observed = frozenset(observed_ids)
    return tuple(ScopeIssue(code, rule_id) for rule_id in expected_ids if rule_id not in observed)


def _unexpected(
    expected_ids: tuple[str, ...], observed_ids: tuple[str, ...], code: ScopeIssueCode
) -> tuple[ScopeIssue, ...]:
    expected = frozenset(expected_ids)
    return tuple(
        ScopeIssue(code, rule_id) for rule_id in sorted(frozenset(observed_ids) - expected)
    )


def check_scope(
    manifest: RuleScopeManifest, inventory: RuleScopeInventory
) -> tuple[ScopeIssue, ...]:
    """Return stable machine issue values for one declared scope and inventory."""
    issues: list[ScopeIssue] = []
    if not manifest.staged:
        code = (
            ScopeIssueCode.UNSTAGED_EMPTY_SCOPE
            if not manifest.expected_ids and not manifest.reserved_ids
            else ScopeIssueCode.UNSTAGED_SCOPE
        )
        issues.append(ScopeIssue(code))
    if len(frozenset(manifest.expected_ids)) != len(manifest.expected_ids):
        issues.append(ScopeIssue(ScopeIssueCode.DUPLICATE_EXPECTED_ID))
    if len(frozenset(manifest.reserved_ids)) != len(manifest.reserved_ids):
        issues.append(ScopeIssue(ScopeIssueCode.DUPLICATE_RESERVED_ID))
    if frozenset(manifest.expected_ids) & frozenset(manifest.reserved_ids):
        issues.append(ScopeIssue(ScopeIssueCode.EXPECTED_RESERVED_OVERLAP))
    if frozenset(inventory.ko_ids) != frozenset(inventory.en_ids):
        issues.append(ScopeIssue(ScopeIssueCode.I18N_PARITY))
    document_ids = (*manifest.expected_ids, *manifest.reserved_ids)
    issues.extend(
        _unexpected(
            manifest.expected_ids,
            inventory.registered_ids,
            ScopeIssueCode.UNEXPECTED_REGISTERED_ID,
        )
    )
    issues.extend(_unexpected(document_ids, inventory.ko_ids, ScopeIssueCode.UNEXPECTED_KO_ID))
    issues.extend(_unexpected(document_ids, inventory.en_ids, ScopeIssueCode.UNEXPECTED_EN_ID))
    issues.extend(
        _unexpected(
            manifest.expected_ids,
            inventory.positive_fixture_ids,
            ScopeIssueCode.UNEXPECTED_POSITIVE_FIXTURE,
        )
    )
    issues.extend(
        _unexpected(
            manifest.expected_ids,
            inventory.negative_fixture_ids,
            ScopeIssueCode.UNEXPECTED_NEGATIVE_FIXTURE,
        )
    )
    issues.extend(
        _missing(
            manifest.expected_ids, inventory.registered_ids, ScopeIssueCode.MISSING_REGISTERED_ID
        )
    )
    issues.extend(_missing(manifest.expected_ids, inventory.ko_ids, ScopeIssueCode.MISSING_KO_ID))
    issues.extend(_missing(manifest.expected_ids, inventory.en_ids, ScopeIssueCode.MISSING_EN_ID))
    issues.extend(
        _missing(
            manifest.reserved_ids,
            inventory.ko_ids,
            ScopeIssueCode.MISSING_RESERVED_KO_ID,
        )
    )
    issues.extend(
        _missing(
            manifest.reserved_ids,
            inventory.en_ids,
            ScopeIssueCode.MISSING_RESERVED_EN_ID,
        )
    )
    issues.extend(
        _missing(
            manifest.expected_ids,
            inventory.positive_fixture_ids,
            ScopeIssueCode.MISSING_POSITIVE_FIXTURE,
        )
    )
    issues.extend(
        _missing(
            manifest.expected_ids,
            inventory.negative_fixture_ids,
            ScopeIssueCode.MISSING_NEGATIVE_FIXTURE,
        )
    )
    return tuple(issues)


__all__ = [
    "RuleScopeInventory",
    "RuleScopeManifest",
    "ScopeIssue",
    "ScopeIssueCode",
    "check_scope",
]
