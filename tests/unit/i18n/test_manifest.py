from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import yaml

from panopticon.i18n.catalog import RULE_IDS

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "src" / "panopticon" / "i18n" / "expected_rules.yaml"


def _load_checker():
    path = ROOT / "scripts" / "check_rules.py"
    spec = importlib.util.spec_from_file_location("check_rules_manifest", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy_manifest(root: Path) -> Path:
    destination = root / "src" / "panopticon" / "i18n" / "expected_rules.yaml"
    destination.parent.mkdir(parents=True)
    shutil.copy(MANIFEST, destination)
    return destination


def test_expected_manifest_has_exact_catalog_parity() -> None:
    payload = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert set(payload["expected_ids"]) == set(RULE_IDS)
    assert len(payload["expected_ids"]) == len(RULE_IDS) == 47
    assert payload["reserved_ids"] == []


def test_generated_catalog_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    script_path = ROOT / "scripts" / "gen_rule_catalog.py"
    spec = importlib.util.spec_from_file_location("catalog_generator", script_path)
    assert spec and spec.loader
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    monkeypatch.setattr(generator, "ROOT", tmp_path)
    (tmp_path / "docs" / "rules").mkdir(parents=True)
    first = generator.main()
    generated = tmp_path / "docs" / "rules" / "CATALOG.md"
    first_bytes = generated.read_bytes()
    second = generator.main()
    assert first == second == 0
    assert generated.read_bytes() == first_bytes


def test_missing_required_doc_fails_manifest(tmp_path: Path) -> None:
    checker = _load_checker()
    manifest = _copy_manifest(tmp_path)
    source = ROOT / "src" / "panopticon" / "i18n"
    for locale in ("ko", "en"):
        destination = tmp_path / "src" / "panopticon" / "i18n" / locale / "rules"
        destination.mkdir(parents=True)
        shutil.copytree(source / locale / "rules", destination, dirs_exist_ok=True)
    (tmp_path / "src" / "panopticon" / "i18n" / "ko" / "rules" / "WATCH-001.md").unlink()
    issues = checker.repository_issues(tmp_path, manifest, manifest)
    assert any(issue.code.value == "MISSING_KO_ID" for issue in issues)
