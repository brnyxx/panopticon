from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from panopticon.cli import analysis_commands as main
from panopticon.cli.main import app
from panopticon.engine.contracts import (
    CompleteResult,
    EngineDiagnostic,
    EngineReason,
    IncompleteResult,
)
from panopticon.engine.scan import ScanFinding, ScanMode, ScanOutcome

runner = CliRunner()


def _outcome(*findings: ScanFinding, incomplete: bool = False) -> ScanOutcome:
    result = (
        IncompleteResult(
            reason_code=EngineReason.DISCOVERY_FAILED,
            diagnostics=(EngineDiagnostic("CACHE_MISSING", "cache"),),
        )
        if incomplete
        else CompleteResult()
    )
    return ScanOutcome(result, tuple(findings), ScanMode.STANDARD, 1 if findings else 0)


def test_ci_persists_valid_sarif_before_success_and_findings_exit(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "report.sarif"
    finding = ScanFinding("SENT-999", "high", "HIGH", "fp", "a.py", 1, 1)
    monkeypatch.setattr(main, "run_scan", lambda request: _outcome(finding))
    checked = []
    original_exit = main.ci_exit_code

    def assert_persisted(outcome, policy, *, sarif_persisted):
        checked.append(target.is_file())
        return original_exit(outcome, policy, sarif_persisted=sarif_persisted)

    monkeypatch.setattr(main, "ci_exit_code", assert_persisted)
    result = runner.invoke(app, ["ci", str(tmp_path), "--sarif", str(target), "--fail-on", "high"])
    assert result.exit_code == 1
    assert checked == [True]
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["version"] == "2.1.0"
    assert payload["runs"][0]["results"][0]["ruleId"] == "SENT-999"

    target.unlink()
    monkeypatch.setattr(main, "run_scan", lambda request: _outcome())
    result = runner.invoke(app, ["ci", str(tmp_path), "--sarif", str(target)])
    assert result.exit_code == 0
    assert json.loads(target.read_text(encoding="utf-8"))["runs"]


def test_ci_incomplete_precedes_findings_and_fail_policies(tmp_path: Path, monkeypatch) -> None:
    finding = ScanFinding("SENT-998", "medium", "MEDIUM", "fp", "a.py", 1, 1)
    monkeypatch.setattr(main, "run_scan", lambda request: _outcome(finding, incomplete=True))
    for policy in ("high", "medium", "incomplete", "never"):
        target = tmp_path / f"{policy}.sarif"
        result = runner.invoke(
            app,
            ["ci", str(tmp_path), "--sarif", str(target), "--fail-on", policy],
        )
        assert result.exit_code == 3
        assert target.is_file()

    monkeypatch.setattr(main, "run_scan", lambda request: _outcome(finding))
    medium = runner.invoke(
        app,
        ["ci", str(tmp_path), "--sarif", str(tmp_path / "m.sarif"), "--fail-on", "medium"],
    )
    assert medium.exit_code == 1
    never = runner.invoke(
        app,
        ["ci", str(tmp_path), "--sarif", str(tmp_path / "n.sarif"), "--fail-on", "never"],
    )
    assert never.exit_code == 0


def test_ci_rejects_bad_mode_and_policy_usage(tmp_path: Path) -> None:
    bad_mode = runner.invoke(app, ["ci", str(tmp_path), "--mode", "bogus"])
    assert bad_mode.exit_code == 2
    bad_policy = runner.invoke(app, ["ci", str(tmp_path), "--fail-on", "bogus"])
    assert bad_policy.exit_code == 2
