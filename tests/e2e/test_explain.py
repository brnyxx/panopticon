from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from panopticon.cli import main as cli
from panopticon.engine.explain import ExplainStatus, explain_rule
from panopticon.i18n.catalog import RULE_IDS
from panopticon.i18n.loader import SECTION_IDS

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "panopticon" / "i18n"


def _inject_root(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    original = cli.explain_rule
    monkeypatch.setattr(
        cli,
        "explain_rule",
        lambda rule_id, *, locale=None: original(rule_id, locale=locale, root=root),
    )


def _write_doc(root: Path, locale: str, rule_id: str, text: str | None = None) -> None:
    destination = root / locale / "rules" / f"{rule_id}.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if text is None:
        text = "\n\n".join(f"## {section}\n{locale}-{rule_id}-{section}" for section in SECTION_IDS)
    destination.write_text(text, encoding="utf-8")


def test_watch_001_explains_in_ko_and_en(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_doc(
        tmp_path,
        "ko",
        "WATCH-001",
        "## Problem\n한국어\n\n" + "\n\n".join(f"## {s}\nko" for s in SECTION_IDS[1:]),
    )
    _write_doc(tmp_path, "en", "WATCH-001")
    _inject_root(monkeypatch, tmp_path)
    ko = runner.invoke(cli.app, ["explain", "WATCH-001", "--lang", "ko"])
    en = runner.invoke(cli.app, ["explain", "WATCH-001", "--lang", "en"])
    assert ko.exit_code == en.exit_code == 0
    assert "한국어" in ko.stdout
    assert all(f"## {section}" in ko.stdout for section in SECTION_IDS)
    assert "en-WATCH-001" in en.stdout


def test_shipped_korean_document_maps_sections_to_canonical_ids() -> None:
    result = runner.invoke(cli.app, ["explain", "WATCH-001", "--lang", "ko", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["locale"] == "ko"
    assert set(payload["sections"]) == set(SECTION_IDS)
    assert "미끼" in payload["sections"]["Problem"]


def test_locale_precedence_explicit_then_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for locale in ("ko", "en"):
        _write_doc(tmp_path, locale, "WATCH-001")
    _inject_root(monkeypatch, tmp_path)
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    monkeypatch.setenv("LC_MESSAGES", "ko_KR.UTF-8")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert runner.invoke(cli.app, ["explain", "WATCH-001"]).stdout.find("en-WATCH") >= 0
    monkeypatch.delenv("LC_ALL")
    assert runner.invoke(cli.app, ["explain", "WATCH-001"]).stdout.find("ko-WATCH") >= 0
    monkeypatch.delenv("LC_MESSAGES")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert runner.invoke(cli.app, ["explain", "WATCH-001"]).stdout.find("en-WATCH") >= 0
    monkeypatch.delenv("LANG")
    assert runner.invoke(cli.app, ["explain", "WATCH-001"]).stdout.find("en-WATCH") >= 0
    assert (
        runner.invoke(cli.app, ["explain", "WATCH-001", "--lang", "fr"]).stdout.find("en-WATCH")
        >= 0
    )
    assert (
        runner.invoke(cli.app, ["explain", "WATCH-001", "--lang", "en"]).stdout.find("en-WATCH")
        >= 0
    )


def test_missing_ko_falls_back_to_english(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_doc(tmp_path, "en", "WATCH-001")
    _inject_root(monkeypatch, tmp_path)
    result = runner.invoke(cli.app, ["explain", "WATCH-001", "--lang", "ko"])
    assert result.exit_code == 0 and "en-WATCH-001" in result.stdout


def test_invalid_and_missing_known_document_are_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inject_root(monkeypatch, tmp_path)
    missing = runner.invoke(cli.app, ["explain", "WATCH-001", "--json"])
    assert missing.exit_code == 3 and json.loads(missing.stderr)["status"] == "INCOMPLETE"
    _write_doc(tmp_path, "en", "WATCH-001", "## Problem\nonly")
    invalid = runner.invoke(cli.app, ["explain", "WATCH-001", "--json"])
    assert (
        invalid.exit_code == 3
        and json.loads(invalid.stderr)["reason_code"] == "INVALID_RULE_DOCUMENT"
    )


def test_unknown_id_and_path_traversal_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inject_root(monkeypatch, tmp_path)
    for value in ("NOPE-999", "../WATCH-001", "WATCH-001/../../x"):
        result = runner.invoke(cli.app, ["explain", value, "--json"])
        assert result.exit_code == 4
        assert json.loads(result.stderr)["status"] == "UNKNOWN"


def test_json_preserves_cjk_and_exact_six_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_doc(
        tmp_path, "en", "WATCH-001", "\n\n".join(f"## {s}\n安全한 설명" for s in SECTION_IDS)
    )
    _inject_root(monkeypatch, tmp_path)
    result = runner.invoke(cli.app, ["explain", "WATCH-001", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload["sections"]) == set(SECTION_IDS)
    assert len(payload["sections"]) == 6
    assert set(payload["sections"].values()) == {"安全한 설명"}


@pytest.mark.parametrize(
    "text",
    [
        "## Problem\nx\n\n## Problem\ny\n" + "\n\n".join(f"## {s}\nz" for s in SECTION_IDS[1:]),
        "\n\n".join(f"## {s}\nz" for s in (*SECTION_IDS[:-1], "Other")),
        "\n\n".join(f"## {s}\n" for s in SECTION_IDS),
    ],
)
def test_duplicate_wrong_or_empty_sections_are_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    _write_doc(tmp_path, "en", "WATCH-001", text)
    _inject_root(monkeypatch, tmp_path)
    result = runner.invoke(cli.app, ["explain", "WATCH-001"])
    assert result.exit_code == 3 and "INCOMPLETE" in result.stderr


def test_all_47_catalog_ids_are_known() -> None:
    assert len(RULE_IDS) == 47
    assert all(
        explain_rule(rule_id, root=SOURCE).status is ExplainStatus.KNOWN for rule_id in RULE_IDS
    )
