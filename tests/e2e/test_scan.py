from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import panopticon.cli.analysis_commands as analysis_commands
from panopticon.analyzers.dependency.model import DependencyInput
from panopticon.analyzers.dependency.scan import AdvisoryResult, AdvisoryStatus, DependencyFinding
from panopticon.analyzers.static.findings import StaticFindingView
from panopticon.cli.main import app
from panopticon.engine.contracts import CompleteResult, EngineStatus
from panopticon.engine.scan import (
    DeepDimension,
    DeepDimensionStatus,
    ScanFinding,
    ScanMode,
    ScanOutcome,
    ScanRequest,
    discover_config,
    run_scan,
)
from panopticon.reporters.scan import render, render_cli


class FakeSemgrep:
    def __init__(self, findings: tuple[StaticFindingView, ...]) -> None:
        self.findings = findings
        self.calls = 0

    def scan(self, root: Path) -> tuple[StaticFindingView, ...]:
        self.calls += 1
        return self.findings


class FakeAdvisory:
    def __init__(self, result: AdvisoryResult) -> None:
        self.result = result
        self.calls = 0

    def check(self, requirements: DependencyInput) -> AdvisoryResult:
        self.calls += 1
        return self.result


class FakeSemantic:
    def __init__(self, result: DeepDimension) -> None:
        self.result = result
        self.calls: list[tuple[Path, tuple[object, ...]]] = []

    def analyze(self, root: Path, findings: tuple[ScanFinding, ...]) -> DeepDimension:
        self.calls.append((root, findings))
        return self.result


class FakeDynamic:
    def __init__(self, result: DeepDimension) -> None:
        self.result = result
        self.calls: list[Path] = []

    def analyze(self, root: Path) -> DeepDimension:
        self.calls.append(root)
        return self.result


def test_cli_offline_is_propagated_to_scan_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[ScanRequest] = []

    def capture(request: ScanRequest) -> ScanOutcome:
        captured.append(request)
        return run_scan(ScanRequest(tmp_path, mode=ScanMode.QUICK))

    monkeypatch.setattr(analysis_commands, "run_scan", capture)
    result = CliRunner().invoke(app, ["scan", str(tmp_path), "--offline", "--json"])

    assert result.exit_code == 0
    assert captured[0].offline is True


def test_quick_and_standard_emit_exact_findings_and_sarif(tmp_path: Path) -> None:
    (tmp_path / "panopticon.toml").write_text(
        '[scan]\nmode = "standard"\nexclude = ["ignored.py"]\n', encoding="utf-8"
    )
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    (tmp_path / "server.py").write_text(
        "@mcp.tool()\ndef search(query):\n    return query\n", encoding="utf-8"
    )
    (tmp_path / "ignored.py").write_text(
        "@mcp.tool()\ndef hidden(value):\n    return value\n", encoding="utf-8"
    )
    semgrep = FakeSemgrep(
        (StaticFindingView("FIX-001", "semantic issue", "MEDIUM", "sem-fp", "src.py", 2, 1),)
    )
    advisory = FakeAdvisory(
        AdvisoryResult(
            AdvisoryStatus.COMPLETE,
            "COMPLETE",
            (DependencyFinding("SENT-011", "requests", "HIGH", "known issue"),),
        )
    )

    quick_semgrep = FakeSemgrep(())
    quick = run_scan(ScanRequest(tmp_path, mode=ScanMode.QUICK, semgrep=quick_semgrep))
    assert quick.status is EngineStatus.COMPLETE
    assert quick.mode is ScanMode.QUICK
    assert [(f.rule_id, f.path, f.line, f.column) for f in quick.findings] == [
        ("SENT-003", "server.py", 2, 12)
    ]
    assert quick_semgrep.calls == 0

    standard = run_scan(
        ScanRequest(tmp_path, mode=ScanMode.STANDARD, semgrep=semgrep, advisory=advisory)
    )
    assert standard.status is EngineStatus.COMPLETE
    assert standard.exit_code == 1
    assert [(f.rule_id, f.path, f.line, f.column) for f in standard.findings] == [
        ("FIX-001", "src.py", 2, 1),
        ("SENT-003", "server.py", 2, 12),
        ("SENT-011", None, None, None),
    ]
    assert semgrep.calls == advisory.calls == 1
    first_sarif = render(standard)
    second_sarif = render(standard)
    assert first_sarif == second_sarif
    payload = json.loads(first_sarif)
    assert [item["ruleId"] for item in payload["runs"][0]["results"]] == [
        "FIX-001",
        "SENT-003",
        "SENT-011",
    ]
    assert (
        payload["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"][
            "uri"
        ]
        == "src.py"
    )


def test_missing_semgrep_or_cache_is_typed_incomplete(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    clean = run_scan(ScanRequest(tmp_path, mode=ScanMode.QUICK))
    assert clean.status is EngineStatus.COMPLETE
    assert clean.exit_code == 0

    missing_semgrep = run_scan(
        ScanRequest(
            tmp_path,
            mode=ScanMode.STANDARD,
            advisory=FakeAdvisory(AdvisoryResult(AdvisoryStatus.COMPLETE, "COMPLETE")),
        )
    )
    assert missing_semgrep.status is EngineStatus.INCOMPLETE
    assert missing_semgrep.exit_code == 3
    assert missing_semgrep.result.diagnostics[0].code == "SEMGREP_UNAVAILABLE"
    assert "Traceback" not in render_cli(missing_semgrep).stderr

    semgrep = FakeSemgrep(())
    missing_cache = run_scan(
        ScanRequest(
            tmp_path,
            mode=ScanMode.STANDARD,
            semgrep=semgrep,
            advisory=FakeAdvisory(AdvisoryResult(AdvisoryStatus.COMPLETE, "COMPLETE")),
            cache_available=False,
        )
    )
    assert missing_cache.status is EngineStatus.INCOMPLETE
    assert missing_cache.exit_code == 3
    assert missing_cache.result.diagnostics[0].code == "ADVISORY_CACHE_UNAVAILABLE"

    offline = run_scan(
        ScanRequest(
            tmp_path,
            mode=ScanMode.STANDARD,
            semgrep=semgrep,
            advisory=FakeAdvisory(AdvisoryResult(AdvisoryStatus.COMPLETE, "COMPLETE")),
            offline=True,
        )
    )
    assert offline.status is EngineStatus.INCOMPLETE
    assert offline.exit_code == 3
    assert offline.result.diagnostics[0].code == "OFFLINE"


def test_deep_runs_standard_then_semantic_and_self_with_deterministic_merge(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    (tmp_path / "server.py").write_text(
        "@mcp.tool()\ndef search(query):\n    return query\n", encoding="utf-8"
    )
    semgrep = FakeSemgrep(
        (StaticFindingView("SENT-002", "semantic", "LOW", "sem-fp", "sem.py", 3, 2),)
    )
    advisory = FakeAdvisory(AdvisoryResult(AdvisoryStatus.COMPLETE, "COMPLETE"))
    semantic = FakeSemantic(
        DeepDimension(
            DeepDimensionStatus.COMPLETE,
            "SEMANTIC_COMPLETE",
            (ScanFinding("SENT-001", "deep semantic", "HIGH", "deep-fp", "a.py", 1, 1),),
        )
    )
    dynamic = FakeDynamic(
        DeepDimension(
            DeepDimensionStatus.COMPLETE,
            "SELF_COMPLETE",
            (ScanFinding("WATCH-001", "self behavior", "MEDIUM", "self-fp", "b.py", 2, 1),),
        )
    )
    outcome = run_scan(
        ScanRequest(
            tmp_path,
            mode=ScanMode.DEEP,
            semgrep=semgrep,
            advisory=advisory,
            semantic=semantic,
            dynamic_self=dynamic,
        )
    )
    assert outcome.status is EngineStatus.COMPLETE
    assert [f.rule_id for f in outcome.findings] == [
        "SENT-001",
        "SENT-002",
        "SENT-003",
        "WATCH-001",
    ]
    assert semantic.calls and semantic.calls[0][1][0].rule_id == "SENT-003"
    assert dynamic.calls == [tmp_path.resolve()]
    assert json.loads(render(outcome)) == json.loads(render(outcome))


def test_deep_missing_or_unsupported_dimensions_are_visible_incomplete(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    advisory = FakeAdvisory(AdvisoryResult(AdvisoryStatus.COMPLETE, "COMPLETE"))
    semgrep = FakeSemgrep(())
    base = {
        "path": tmp_path,
        "mode": ScanMode.DEEP,
        "semgrep": semgrep,
        "advisory": advisory,
    }
    missing = run_scan(ScanRequest(**base))
    assert missing.exit_code == 3
    assert missing.result.diagnostics[0].code == "SEMANTIC_ANALYZER_UNAVAILABLE"
    unsupported = run_scan(
        ScanRequest(
            **base,
            semantic=FakeSemantic(
                DeepDimension(DeepDimensionStatus.UNSUPPORTED, "SEMANTIC_UNSUPPORTED")
            ),
            dynamic_self=FakeDynamic(DeepDimension(DeepDimensionStatus.COMPLETE, "SELF_COMPLETE")),
        )
    )
    assert unsupported.exit_code == 3
    assert unsupported.result.diagnostics[0].code == "SEMANTIC_UNSUPPORTED"
    assert unsupported.result.diagnostics[0].code == "SEMANTIC_UNSUPPORTED"


def test_explicit_config_path_is_honored_and_traversal_rejected(tmp_path: Path) -> None:
    config = tmp_path / "custom.toml"
    config.write_text('[scan]\nmode = "standard"\nexclude = ["server.py"]\n', encoding="utf-8")
    (tmp_path / "server.py").write_text(
        "@mcp.tool()\ndef search(q):\n return q\n", encoding="utf-8"
    )
    selected = discover_config(tmp_path, config)
    assert selected.mode is ScanMode.STANDARD
    assert selected.scanner.ignore_paths == ("server.py",)
    try:
        discover_config(tmp_path, Path("../outside.toml"))
    except ValueError as error:
        assert str(error) == "SCAN_CONFIG_OUT_OF_SCOPE"
    else:
        raise AssertionError("config traversal must be rejected")


def test_watch_self_selection_and_conflicts(monkeypatch) -> None:
    from panopticon.cli import main
    from panopticon.engine.watch_service import WatchServiceOutcome

    seen = []

    def fake_watch(request):
        seen.append(request)
        return WatchServiceOutcome(CompleteResult())

    monkeypatch.setattr(main.engine, "run_watch", fake_watch)
    runner = CliRunner()
    assert runner.invoke(app, ["watch", "--self"]).exit_code == 0
    assert seen[0].selection.mode.value == "self"
    assert runner.invoke(app, ["watch", "named", "--self"]).exit_code == 2
