from __future__ import annotations

import json
from pathlib import Path

from panopticon.analyzers.dependency.model import DependencyInput
from panopticon.analyzers.dependency.scan import AdvisoryResult, AdvisoryStatus, DependencyFinding
from panopticon.analyzers.static.findings import StaticFindingView
from panopticon.engine.contracts import EngineStatus
from panopticon.engine.scan import ScanMode, ScanRequest, run_scan
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
