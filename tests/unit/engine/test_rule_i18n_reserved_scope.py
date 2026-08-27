"""Contracts for explicitly reserved rule documentation scope."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Final

import pytest

from panopticon.rules.scope import (
    RuleScopeInventory,
    RuleScopeManifest,
    ScopeIssue,
    ScopeIssueCode,
)

ROOT = Path(__file__).resolve().parents[3]
EXPECTED_RULE_SCOPE = ROOT / "src" / "panopticon" / "rules" / "expected_scope.yaml"
EXPECTED_I18N_SCOPE = ROOT / "src" / "panopticon" / "i18n" / "expected_rules.yaml"
sys.path.insert(0, str(ROOT / "scripts"))
check_rules = importlib.import_module("check_rules")


@dataclass(frozen=True, slots=True)
class _TestRuleScopeManifest:
    """Structural manifest fixture for the dynamically loaded checker seam."""

    staged: bool
    expected_ids: tuple[str, ...]
    reserved_ids: tuple[str, ...] = ()


RESERVED_MANIFEST: Final = _TestRuleScopeManifest(
    staged=True,
    expected_ids=(),
    reserved_ids=("WATCH-001",),
)


def _codes(issues: tuple[ScopeIssue, ...]) -> frozenset[ScopeIssueCode]:
    """Return stable issue codes without depending on issue ordering."""
    return frozenset(issue.code for issue in issues)


def _loader() -> Callable[[Path], tuple[RuleScopeManifest | None, ScopeIssue | None]]:
    """Load the manifest parser seam from the checker script."""
    loader: Callable[[Path], tuple[RuleScopeManifest | None, ScopeIssue | None]] | None = getattr(
        check_rules, "_load_manifest", None
    )
    assert loader is not None and callable(loader), "manifest loader is missing"
    return loader


def _scope_checker() -> Callable[
    [_TestRuleScopeManifest, RuleScopeInventory], tuple[ScopeIssue, ...]
]:
    """Load the scope checker using the structural test manifest fixture."""
    module = importlib.import_module("panopticon.rules.scope")
    checker: (
        Callable[[_TestRuleScopeManifest, RuleScopeInventory], tuple[ScopeIssue, ...]] | None
    ) = getattr(module, "check_scope", None)
    assert checker is not None and callable(checker), "scope checker is missing"
    return checker


def test_rule_scope_manifest_separates_reserved_and_active_ids() -> None:
    # Given: the production manifest dataclass.
    manifest_fields = {field.name for field in fields(RuleScopeManifest)}

    # When: its declared fields are inspected.
    # Then: active and reserved scope have separate typed fields.
    assert {"expected_ids", "reserved_ids"} <= manifest_fields


def test_current_manifests_explicitly_reserve_only_watch001() -> None:
    # Given: the two tracked scope manifests.
    load_manifest = _loader()

    # When: both manifests are parsed.
    loaded = [load_manifest(path) for path in (EXPECTED_RULE_SCOPE, EXPECTED_I18N_SCOPE)]

    # Then: both declare the same staged, empty-active, WATCH-001-reserved scope.
    for manifest, issue in loaded:
        assert issue is None
        assert manifest is not None
        assert manifest.staged is True
        assert manifest.expected_ids == ()
        assert getattr(manifest, "reserved_ids", None) == ("WATCH-001",)

    assert check_rules.repository_issues(ROOT, EXPECTED_RULE_SCOPE, EXPECTED_I18N_SCOPE) == ()


def test_reserved_bilingual_docs_are_allowed_without_active_assets() -> None:
    # Given: reserved WATCH-001 docs in both languages and no active assets.
    inventory = RuleScopeInventory((), ("WATCH-001",), ("WATCH-001",), (), ())

    # When: the reserved scope is checked.
    issues = _scope_checker()(RESERVED_MANIFEST, inventory)

    # Then: documentation-only reservation is valid.
    assert issues == ()


@pytest.mark.parametrize(
    ("ko_ids", "en_ids", "expected_code"),
    (
        (("WATCH-001",), (), "MISSING_RESERVED_EN_ID"),
        ((), ("WATCH-001",), "MISSING_RESERVED_KO_ID"),
    ),
    ids=("missing-en", "missing-ko"),
)
def test_reserved_docs_require_both_languages(
    ko_ids: tuple[str, ...],
    en_ids: tuple[str, ...],
    expected_code: str,
) -> None:
    # Given: a reserved ID documented in only one language.
    inventory = RuleScopeInventory((), ko_ids, en_ids, (), ())

    # When: the reserved scope is checked.
    issues = _scope_checker()(RESERVED_MANIFEST, inventory)

    # Then: the absent language has a deterministic reserved-document issue.
    assert expected_code in _codes(issues)


def test_unlisted_document_remains_unexpected_while_reserved_docs_are_allowed() -> None:
    # Given: both reserved docs plus one unlisted Korean document.
    inventory = RuleScopeInventory(
        registered_ids=(),
        ko_ids=("WATCH-001", "EXTRA-001"),
        en_ids=("WATCH-001",),
        positive_fixture_ids=(),
        negative_fixture_ids=(),
    )

    # When: the reserved scope is checked.
    issues = _scope_checker()(RESERVED_MANIFEST, inventory)

    # Then: only the unlisted document is unexpected; reserved WATCH-001 is accepted.
    assert ScopeIssue(ScopeIssueCode.UNEXPECTED_KO_ID, "EXTRA-001") in issues
    assert ScopeIssue(ScopeIssueCode.UNEXPECTED_KO_ID, "WATCH-001") not in issues


def test_reserved_ids_do_not_satisfy_active_registration_or_fixtures() -> None:
    # Given: reserved WATCH-001 has an active registration and both fixture directions.
    inventory = RuleScopeInventory(
        registered_ids=("WATCH-001",),
        ko_ids=("WATCH-001",),
        en_ids=("WATCH-001",),
        positive_fixture_ids=("WATCH-001",),
        negative_fixture_ids=("WATCH-001",),
    )

    # When: the reserved scope is checked.
    issues = _scope_checker()(RESERVED_MANIFEST, inventory)
    codes = _codes(issues)

    # Then: active assets are rejected, while reserved docs need no fixtures.
    assert {
        ScopeIssueCode.UNEXPECTED_REGISTERED_ID,
        ScopeIssueCode.UNEXPECTED_POSITIVE_FIXTURE,
        ScopeIssueCode.UNEXPECTED_NEGATIVE_FIXTURE,
    } <= codes
    assert (
        not {
            ScopeIssueCode.UNEXPECTED_KO_ID,
            ScopeIssueCode.UNEXPECTED_EN_ID,
            ScopeIssueCode.MISSING_REGISTERED_ID,
            ScopeIssueCode.MISSING_POSITIVE_FIXTURE,
            ScopeIssueCode.MISSING_NEGATIVE_FIXTURE,
        }
        & codes
    )


def test_duplicate_reserved_id_is_rejected() -> None:
    # Given: a manifest that lists one reserved ID twice.
    manifest = _TestRuleScopeManifest(
        staged=True,
        expected_ids=(),
        reserved_ids=("WATCH-001", "WATCH-001"),
    )

    # When: the scope is checked.
    issues = _scope_checker()(manifest, RuleScopeInventory((), (), (), (), ()))

    # Then: duplicate reserved entries produce a machine issue.
    assert "DUPLICATE_RESERVED_ID" in _codes(issues)


def test_expected_and_reserved_overlap_is_rejected() -> None:
    # Given: one ID listed as both active and reserved.
    manifest = _TestRuleScopeManifest(
        staged=True,
        expected_ids=("WATCH-001",),
        reserved_ids=("WATCH-001",),
    )

    # When: the scope is checked.
    issues = _scope_checker()(manifest, RuleScopeInventory((), (), (), (), ()))

    # Then: overlapping scope declarations produce a machine issue.
    assert "EXPECTED_RESERVED_OVERLAP" in _codes(issues)


def test_manifest_without_reserved_ids_is_invalid(tmp_path: Path) -> None:
    # Given: a legacy-shaped manifest without an explicit reserved_ids list.
    path = tmp_path / "expected_scope.yaml"
    path.write_text("version: 1\nstaged: true\nexpected_ids: []\n", encoding="utf-8")
    load_manifest = _loader()

    # When: the manifest is parsed.
    manifest, issue = load_manifest(path)

    # Then: omission of reserved scope is a deterministic manifest error.
    assert manifest is None
    assert issue is not None
    assert issue.code is ScopeIssueCode.INVALID_SCOPE_MANIFEST


def test_rule_and_i18n_reserved_scope_must_match(tmp_path: Path) -> None:
    # Given: rule and i18n manifests that differ only in their reserved IDs.
    rule_manifest = tmp_path / "rules" / "expected_scope.yaml"
    i18n_manifest = tmp_path / "i18n" / "expected_rules.yaml"
    rule_manifest.parent.mkdir()
    i18n_manifest.parent.mkdir()
    rule_manifest.write_text(
        "version: 1\nstaged: true\nexpected_ids: []\nreserved_ids: [WATCH-001]\n",
        encoding="utf-8",
    )
    i18n_manifest.write_text(
        "version: 1\nstaged: true\nexpected_ids: []\nreserved_ids: [WATCH-002]\n",
        encoding="utf-8",
    )

    # When: the repository checker compares the declarations.
    issues = check_rules.repository_issues(
        tmp_path,
        rule_manifest,
        i18n_manifest,
        RuleScopeInventory((), (), (), (), ()),
    )

    # Then: the mismatch is reported before inventory semantics are evaluated.
    assert ScopeIssueCode.MANIFEST_SCOPE_MISMATCH in _codes(issues)


def test_promoting_reserved_id_to_expected_requires_active_assets() -> None:
    # Given: WATCH-001 has been explicitly moved from reserved to active scope.
    manifest = _TestRuleScopeManifest(
        staged=True,
        expected_ids=("WATCH-001",),
        reserved_ids=(),
    )
    inventory = RuleScopeInventory(
        registered_ids=(),
        ko_ids=("WATCH-001",),
        en_ids=("WATCH-001",),
        positive_fixture_ids=(),
        negative_fixture_ids=(),
    )

    # When: the promoted active scope is checked.
    issues = _scope_checker()(manifest, inventory)
    codes = _codes(issues)

    # Then: registration and both fixture directions are required after promotion.
    assert {
        ScopeIssueCode.MISSING_REGISTERED_ID,
        ScopeIssueCode.MISSING_POSITIVE_FIXTURE,
        ScopeIssueCode.MISSING_NEGATIVE_FIXTURE,
    } <= codes
    assert (
        not {
            ScopeIssueCode.MISSING_KO_ID,
            ScopeIssueCode.MISSING_EN_ID,
        }
        & codes
    )
