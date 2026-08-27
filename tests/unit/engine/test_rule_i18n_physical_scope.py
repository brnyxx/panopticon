"""Filesystem-backed contracts for physical rule and fixture scope assets."""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EXPECTED_RULE_SCOPE = ROOT / "src" / "panopticon" / "rules" / "expected_scope.yaml"
EXPECTED_I18N_SCOPE = ROOT / "src" / "panopticon" / "i18n" / "expected_rules.yaml"
sys.path.insert(0, str(ROOT / "scripts"))
check_rules = importlib.import_module("check_rules")

PHYSICAL_EXTRA_CASES: tuple[tuple[str, str], ...] = (
    ("ko-doc", "UNEXPECTED_KO_ID"),
    ("en-doc", "UNEXPECTED_EN_ID"),
    ("positive-fixture", "UNEXPECTED_POSITIVE_FIXTURE"),
    ("negative-fixture", "UNEXPECTED_NEGATIVE_FIXTURE"),
)


def _copy_staged_zero_manifests(root: Path) -> tuple[Path, Path]:
    """Stand up only the explicit scope manifests in a disposable repository root."""
    rule_manifest = root / "src" / "panopticon" / "rules" / "expected_scope.yaml"
    i18n_manifest = root / "src" / "panopticon" / "i18n" / "expected_rules.yaml"
    rule_manifest.parent.mkdir(parents=True)
    i18n_manifest.parent.mkdir(parents=True)
    shutil.copy(EXPECTED_RULE_SCOPE, rule_manifest)
    shutil.copy(EXPECTED_I18N_SCOPE, i18n_manifest)
    return rule_manifest, i18n_manifest


def _copy_physical_extra(root: Path, asset: str) -> None:
    """Create one physical extra source without using an in-memory inventory."""
    if asset == "ko-doc":
        destination = root / "src" / "panopticon" / "i18n" / "ko" / "rules" / "EXTRA-001.md"
        destination.parent.mkdir(parents=True)
        shutil.copy(
            ROOT / "src" / "panopticon" / "i18n" / "ko" / "rules" / "WATCH-001.md", destination
        )
    elif asset == "en-doc":
        destination = root / "src" / "panopticon" / "i18n" / "en" / "rules" / "EXTRA-001.md"
        destination.parent.mkdir(parents=True)
        shutil.copy(
            ROOT / "src" / "panopticon" / "i18n" / "en" / "rules" / "WATCH-001.md", destination
        )
    elif asset == "positive-fixture":
        destination = root / "tests" / "fixtures" / "rules" / "EXTRA-001" / "positive_case.json"
        destination.parent.mkdir(parents=True)
        destination.touch()
    else:
        destination = root / "tests" / "fixtures" / "rules" / "EXTRA-001" / "negative_case.json"
        destination.parent.mkdir(parents=True)
        destination.touch()


@pytest.mark.parametrize(
    ("asset", "expected_code"),
    PHYSICAL_EXTRA_CASES,
    ids=("ko-doc", "en-doc", "positive-fixture", "negative-fixture"),
)
def test_repository_collection_reports_physical_extra_ids(
    tmp_path: Path,
    asset: str,
    expected_code: str,
) -> None:
    # Given: a disposable repository with explicit staged-zero manifests and one physical extra.
    rule_manifest, i18n_manifest = _copy_staged_zero_manifests(tmp_path)
    _copy_physical_extra(tmp_path, asset)

    # When: the default repository collection runs twice without an injected inventory.
    first = check_rules.repository_issues(tmp_path, rule_manifest, i18n_manifest)
    second = check_rules.repository_issues(tmp_path, rule_manifest, i18n_manifest)

    # Then: the physical extra is reported deterministically with its machine code.
    assert first == second
    assert expected_code in {issue.code.value for issue in first}
