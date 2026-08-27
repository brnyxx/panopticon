"""Validate registered rule scope, bilingual docs, and fixture directions."""

from __future__ import annotations

import importlib
import pkgutil
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Final, cast

import yaml

import panopticon.analyzers as analyzers
from panopticon.rules.registry import all_rules
from panopticon.rules.scope import (
    RuleScopeInventory,
    RuleScopeManifest,
    ScopeIssue,
    ScopeIssueCode,
    check_scope,
)

ROOT: Final = Path(__file__).resolve().parents[1]
RULE_SCOPE: Final = ROOT / "src" / "panopticon" / "rules" / "expected_scope.yaml"
I18N_SCOPE: Final = ROOT / "src" / "panopticon" / "i18n" / "expected_rules.yaml"


def import_all_rules() -> None:
    for module in pkgutil.walk_packages(analyzers.__path__, analyzers.__name__ + "."):
        if module.name.endswith(".rules"):
            importlib.import_module(module.name)


def _load_manifest(path: Path) -> tuple[RuleScopeManifest | None, ScopeIssue | None]:
    if not path.is_file():
        return None, ScopeIssue(ScopeIssueCode.MISSING_SCOPE_MANIFEST, str(path))
    try:
        raw = cast(object, yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError):
        return None, ScopeIssue(ScopeIssueCode.INVALID_SCOPE_MANIFEST, str(path))
    if raw is None:
        return RuleScopeManifest(staged=False, expected_ids=(), reserved_ids=()), None
    if not isinstance(raw, dict):
        return None, ScopeIssue(ScopeIssueCode.INVALID_SCOPE_MANIFEST, str(path))
    document = cast(Mapping[object, object], raw)
    version = document.get("version")
    staged = document.get("staged")
    expected_values = document.get("expected_ids")
    reserved_values = document.get("reserved_ids")
    if (
        version != 1
        or not isinstance(staged, bool)
        or not isinstance(expected_values, list)
        or not isinstance(reserved_values, list)
    ):
        return None, ScopeIssue(ScopeIssueCode.INVALID_SCOPE_MANIFEST, str(path))
    expected_ids: list[str] = []
    for value in expected_values:
        if not isinstance(value, str):
            return None, ScopeIssue(ScopeIssueCode.INVALID_SCOPE_MANIFEST, str(path))
        expected_ids.append(value)
    reserved_ids: list[str] = []
    for value in reserved_values:
        if not isinstance(value, str):
            return None, ScopeIssue(ScopeIssueCode.INVALID_SCOPE_MANIFEST, str(path))
        reserved_ids.append(value)
    return (
        RuleScopeManifest(
            staged=staged,
            expected_ids=tuple(expected_ids),
            reserved_ids=tuple(reserved_ids),
        ),
        None,
    )


def _document_ids(root: Path, language: str) -> tuple[str, ...]:
    directory = root / "src" / "panopticon" / "i18n" / language / "rules"
    if not directory.is_dir():
        return ()
    return tuple(sorted(path.stem for path in directory.glob("*.md")))


def _fixture_ids(root: Path, prefix: str) -> tuple[str, ...]:
    directory = root / "tests" / "fixtures" / "rules"
    if not directory.is_dir():
        return ()
    return tuple(
        sorted(
            child.name
            for child in directory.iterdir()
            if child.is_dir() and any(child.glob(f"{prefix}_*"))
        )
    )


def _inventory(root: Path) -> RuleScopeInventory:
    import_all_rules()
    return RuleScopeInventory(
        registered_ids=tuple(sorted(all_rules())),
        ko_ids=_document_ids(root, "ko"),
        en_ids=_document_ids(root, "en"),
        positive_fixture_ids=_fixture_ids(root, "positive"),
        negative_fixture_ids=_fixture_ids(root, "negative"),
    )


def repository_issues(
    root: Path,
    rule_manifest: Path,
    i18n_manifest: Path,
    inventory: RuleScopeInventory | None = None,
) -> tuple[ScopeIssue, ...]:
    """Return deterministic machine issues for an injected repository scope."""
    rule_scope, rule_issue = _load_manifest(rule_manifest)
    i18n_scope, i18n_issue = _load_manifest(i18n_manifest)
    manifest_issues = tuple(issue for issue in (rule_issue, i18n_issue) if issue is not None)
    if manifest_issues:
        return manifest_issues
    if rule_scope is None or i18n_scope is None:
        return (ScopeIssue(ScopeIssueCode.INVALID_SCOPE_MANIFEST),)
    issues: list[ScopeIssue] = []
    if (
        rule_scope.staged,
        rule_scope.expected_ids,
        rule_scope.reserved_ids,
    ) != (
        i18n_scope.staged,
        i18n_scope.expected_ids,
        i18n_scope.reserved_ids,
    ):
        issues.append(ScopeIssue(ScopeIssueCode.MANIFEST_SCOPE_MISMATCH))
    observed = _inventory(root) if inventory is None else inventory
    issues.extend(check_scope(rule_scope, observed))
    return tuple(issues)


def check_repository(root: Path, rule_manifest: Path, i18n_manifest: Path) -> int:
    """Return zero only when the injected repository has an explicit valid scope."""
    return 0 if not repository_issues(root, rule_manifest, i18n_manifest) else 1


def main() -> int:
    issues = repository_issues(ROOT, RULE_SCOPE, I18N_SCOPE)
    for issue in issues:
        subject = "" if issue.subject is None else f":{issue.subject}"
        print(f"{issue.code}{subject}")
    print(f"checked rule scope, {len(issues)} problem(s)")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
