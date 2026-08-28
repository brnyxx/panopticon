"""RED contracts for non-vacuous rule and ko/en i18n scope checking."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EXPECTED_RULE_SCOPE = ROOT / "src" / "panopticon" / "rules" / "expected_scope.yaml"
EXPECTED_I18N_SCOPE = ROOT / "src" / "panopticon" / "i18n" / "expected_rules.yaml"
sys.path.insert(0, str(ROOT / "scripts"))
check_rules = importlib.import_module("check_rules")


@dataclass(frozen=True, slots=True)
class RuleScopeManifest:
    """Typed expected rule scope supplied by the staged manifest."""

    staged: bool
    expected_ids: tuple[str, ...]
    reserved_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RuleScopeInventory:
    """Typed observed registry, docs, and fixture IDs."""

    registered_ids: tuple[str, ...]
    ko_ids: tuple[str, ...]
    en_ids: tuple[str, ...]
    positive_fixture_ids: tuple[str, ...]
    negative_fixture_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScopeIssue:
    """Machine issue shape returned by the scope checker."""

    code: str


def _scope_checker() -> Callable[[RuleScopeManifest, RuleScopeInventory], tuple[ScopeIssue, ...]]:
    """Load the expected scope seam without causing collection failure."""
    try:
        spec = importlib.util.find_spec("panopticon.rules.scope")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "rule/i18n scope contract is missing"
    module = importlib.import_module("panopticon.rules.scope")
    checker: Callable[[RuleScopeManifest, RuleScopeInventory], tuple[ScopeIssue, ...]] | None = (
        getattr(module, "check_scope", None)
    )
    assert checker is not None and callable(checker), "rule/i18n scope checker is missing"
    return checker


def _codes(issues: tuple[ScopeIssue, ...]) -> frozenset[str]:
    """Return stable issue codes only."""
    return frozenset(issue.code for issue in issues)


def _empty_inventory() -> RuleScopeInventory:
    """Build the explicit all-empty staged fixture."""
    return RuleScopeInventory((), (), (), (), ())


def test_expected_rule_and_i18n_manifests_are_declared() -> None:
    # Given: the two machine-readable scope manifests owned by the foundation.
    # When: their paths are resolved from the package tree.
    # Then: an empty registry cannot silently stand in for an explicit staged scope.
    assert EXPECTED_RULE_SCOPE.is_file()
    assert EXPECTED_I18N_SCOPE.is_file()


def test_staged_zero_rule_scope_is_explicitly_valid() -> None:
    # Given: zero rules with an explicit staged-zero manifest marker.
    check_scope = _scope_checker()
    manifest = RuleScopeManifest(staged=True, expected_ids=())

    # When: the registry and bilingual fixture inventory are checked.
    issues = check_scope(manifest, _empty_inventory())

    # Then: explicit staged zero is the only empty inventory that can pass.
    assert _codes(issues) == frozenset()


EXTRA_SCOPE_CASES: tuple[tuple[str, str, RuleScopeInventory], ...] = (
    (
        "registered",
        "UNEXPECTED_REGISTERED_ID",
        RuleScopeInventory(("EXTRA-001",), (), (), (), ()),
    ),
    (
        "ko",
        "UNEXPECTED_KO_ID",
        RuleScopeInventory((), ("EXTRA-001",), (), (), ()),
    ),
    (
        "en",
        "UNEXPECTED_EN_ID",
        RuleScopeInventory((), (), ("EXTRA-001",), (), ()),
    ),
    (
        "positive-fixture",
        "UNEXPECTED_POSITIVE_FIXTURE",
        RuleScopeInventory((), (), (), ("EXTRA-001",), ()),
    ),
    (
        "negative-fixture",
        "UNEXPECTED_NEGATIVE_FIXTURE",
        RuleScopeInventory((), (), (), (), ("EXTRA-001",)),
    ),
)


@pytest.mark.parametrize(
    ("observed_field", "expected_code", "inventory"),
    EXTRA_SCOPE_CASES,
    ids=("registered", "ko", "en", "positive-fixture", "negative-fixture"),
)
def test_staged_zero_scope_rejects_every_extra_observed_id(
    observed_field: str,
    expected_code: str,
    inventory: RuleScopeInventory,
) -> None:
    # Given: an explicitly staged-zero scope with one extra observed item.
    check_scope = _scope_checker()
    manifest = RuleScopeManifest(staged=True, expected_ids=())

    # When: the scope is checked.
    issues = check_scope(manifest, inventory)

    # Then: every observed source has a deterministic unexpected-item code.
    assert expected_code in _codes(issues), observed_field


def test_unstaged_zero_rule_scope_is_not_vacuously_valid() -> None:
    # Given: zero rules without an explicit staged scope marker.
    check_scope = _scope_checker()
    manifest = RuleScopeManifest(staged=False, expected_ids=())

    # When: the empty inventory is checked.
    issues = check_scope(manifest, _empty_inventory())

    # Then: the machine contract identifies the missing staged declaration.
    assert "UNSTAGED_EMPTY_SCOPE" in _codes(issues)


def test_missing_expected_rule_id_is_reported() -> None:
    # Given: an expected existing rule ID absent from the registered/doc/fixture sets.
    check_scope = _scope_checker()
    manifest = RuleScopeManifest(staged=True, expected_ids=("WATCH-001",))

    # When: the scope is checked.
    issues = check_scope(manifest, _empty_inventory())

    # Then: empty sets do not make the missing rule pass.
    assert {"MISSING_REGISTERED_ID", "MISSING_KO_ID", "MISSING_EN_ID"} <= _codes(issues)


def test_duplicate_expected_rule_id_is_reported() -> None:
    # Given: one ID listed twice in an otherwise complete staged scope.
    check_scope = _scope_checker()
    manifest = RuleScopeManifest(staged=True, expected_ids=("WATCH-001", "WATCH-001"))
    inventory = RuleScopeInventory(
        registered_ids=("WATCH-001",),
        ko_ids=("WATCH-001",),
        en_ids=("WATCH-001",),
        positive_fixture_ids=("WATCH-001",),
        negative_fixture_ids=("WATCH-001",),
    )

    # When: the scope is checked.
    issues = check_scope(manifest, inventory)

    # Then: duplicate manifest entries fail explicitly.
    assert "DUPLICATE_EXPECTED_ID" in _codes(issues)


@pytest.mark.parametrize(
    ("positive_ids", "negative_ids", "expected"),
    (
        ((), ("WATCH-001",), "MISSING_POSITIVE_FIXTURE"),
        (("WATCH-001",), (), "MISSING_NEGATIVE_FIXTURE"),
    ),
)
def test_registered_rule_requires_both_fixture_directions(
    positive_ids: tuple[str, ...],
    negative_ids: tuple[str, ...],
    expected: str,
) -> None:
    # Given: a registered bilingual rule with one fixture direction absent.
    check_scope = _scope_checker()
    manifest = RuleScopeManifest(staged=True, expected_ids=("WATCH-001",))
    inventory = RuleScopeInventory(
        registered_ids=("WATCH-001",),
        ko_ids=("WATCH-001",),
        en_ids=("WATCH-001",),
        positive_fixture_ids=positive_ids,
        negative_fixture_ids=negative_ids,
    )

    # When: the scope is checked.
    issues = check_scope(manifest, inventory)

    # Then: fixture coverage is not made vacuous by one present direction.
    assert expected in _codes(issues)


def test_registered_ko_en_parity_is_checked_even_when_registry_is_empty() -> None:
    # Given: a staged zero registry but a stray bilingual document on one side.
    check_scope = _scope_checker()
    manifest = RuleScopeManifest(staged=True, expected_ids=())
    inventory = RuleScopeInventory((), ("WATCH-001",), (), (), ())

    # When: the scope is checked.
    issues = check_scope(manifest, inventory)

    # Then: parity is a separate non-vacuous invariant.
    assert "I18N_PARITY" in _codes(issues)


def _repository_issue_checker() -> Callable[
    [Path, Path, Path, RuleScopeInventory], tuple[ScopeIssue, ...]
]:
    """Load the repository checker seam with an injectable observed inventory."""
    checker: Callable[[Path, Path, Path, RuleScopeInventory], tuple[ScopeIssue, ...]] | None = (
        getattr(check_rules, "repository_issues", None)
    )
    assert checker is not None and callable(checker), "repository issue checker is missing"
    return checker


def _repository_scope_checker() -> Callable[[Path, Path, Path], int]:
    """Load the checker seam that accepts explicit repository and manifest paths."""
    checker: Callable[[Path, Path, Path], int] | None = getattr(
        check_rules, "check_repository", None
    )
    assert checker is not None and callable(checker), "repository scope checker is missing"
    return checker


def test_injected_repository_zero_scope_rejects_extra_observed_sources() -> None:
    # Given: the real repository paths and a fully injected extra-item inventory.
    repository_issues = _repository_issue_checker()
    inventory = RuleScopeInventory(
        registered_ids=("EXTRA-001",),
        ko_ids=("EXTRA-001",),
        en_ids=("EXTRA-001",),
        positive_fixture_ids=("EXTRA-001",),
        negative_fixture_ids=("EXTRA-001",),
    )

    # When: the repository checker evaluates the staged-zero manifests.
    issues = repository_issues(ROOT, EXPECTED_RULE_SCOPE, EXPECTED_I18N_SCOPE, inventory)

    # Then: injected extra sources cannot make an empty scope pass.
    assert {
        "UNEXPECTED_REGISTERED_ID",
        "UNEXPECTED_KO_ID",
        "UNEXPECTED_EN_ID",
        "UNEXPECTED_POSITIVE_FIXTURE",
        "UNEXPECTED_NEGATIVE_FIXTURE",
    } <= _codes(issues)


def test_repository_with_active_cfg_hist_manifests_is_green() -> None:
    # Given: the current active catalogs and reserved bilingual documentation.
    repository_issues = _repository_issue_checker()
    active = tuple(
        [f"CFG-{index:03d}" for index in range(1, 13)]
        + [f"HIST-{index:03d}" for index in range(1, 5)]
    )
    inventory = RuleScopeInventory(
        registered_ids=active,
        ko_ids=(*active, "WATCH-001"),
        en_ids=(*active, "WATCH-001"),
        positive_fixture_ids=active,
        negative_fixture_ids=active,
    )

    # When / Then: the staged active registry is a successful clean check.
    assert repository_issues(ROOT, EXPECTED_RULE_SCOPE, EXPECTED_I18N_SCOPE, inventory) == ()


INVALID_MANIFEST_CASES: tuple[tuple[str, Path, Path], ...] = (
    (
        "missing",
        ROOT / "tests" / "fixtures" / "rules" / "missing-expected-scope.yaml",
        ROOT / "tests" / "fixtures" / "rules" / "missing-expected-i18n.yaml",
    ),
    (
        "unstaged-empty",
        ROOT / "tests" / "fixtures" / "rules" / ".gitkeep",
        ROOT / "tests" / "fixtures" / "rules" / ".gitkeep",
    ),
)


@pytest.mark.parametrize(
    ("case", "rule_manifest", "i18n_manifest"), INVALID_MANIFEST_CASES, ids=lambda value: value
)
def test_repository_scope_rejects_missing_or_unstaged_empty_manifests(
    case: str,
    rule_manifest: Path,
    i18n_manifest: Path,
) -> None:
    # Given: an injectable repository scope with a missing or unstaged empty manifest.
    check_repository = _repository_scope_checker()

    # When: the checker runs without mutating the repository.
    result = check_repository(ROOT, rule_manifest, i18n_manifest)

    # Then: invalid scope is a non-success machine result.
    assert result != 0, case
