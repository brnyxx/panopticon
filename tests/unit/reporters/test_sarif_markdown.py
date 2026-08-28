from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from panopticon.reporters.markdown import render_markdown
from panopticon.reporters.model import DiagnosticView, SanitizedRenderModel, StageView
from panopticon.reporters.report_bundle import ReportBundle, ReportFinding
from panopticon.reporters.sarif import SARIF_SCHEMA_URI, render, render_sarif

FIXTURE = Path(__file__).parents[2] / "fixtures" / "reporters" / "mixed_report.json"
SECRET = "sk-proj-abcdefghijklmnopqrstuvwxyz1234"


def _bundle() -> ReportBundle:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw_model = data["model"]
    model = SanitizedRenderModel(
        status=raw_model["status"],
        reason_code=raw_model["reason_code"],
        stages=tuple(
            StageView(
                stage["name"],
                stage["status"],
                stage["reason_code"],
                tuple(DiagnosticView(d["code"], d["detail"]) for d in stage.get("diagnostics", ())),
            )
            for stage in raw_model["stages"]
        ),
        diagnostics=tuple(DiagnosticView(d["code"], d["detail"]) for d in raw_model["diagnostics"]),
        evidence_count=raw_model["evidence_count"],
        excluded_allowlist_count=raw_model["excluded_allowlist_count"],
        suppression_count=raw_model["suppression_count"],
    )
    findings = tuple(ReportFinding(**finding) for finding in data["findings"])
    return ReportBundle(model, findings, data["category"])


def test_mixed_findings_render_valid_sarif_and_markdown() -> None:
    report = _bundle()
    first = render_sarif(report)
    second = render_sarif(report)
    payload = json.loads(first)
    run = payload["runs"][0]
    results = run["results"]

    assert first == second
    assert payload["$schema"] == SARIF_SCHEMA_URI
    assert payload["version"] == "2.1.0"
    assert len(payload["runs"]) == 1
    assert run["tool"]["driver"]["name"] == "Panopticon"
    assert run["automationDetails"]["id"] == quote(report.category, safe="/._-")
    assert [rule["id"] for rule in run["tool"]["driver"]["rules"]] == [
        "CFG-001",
        "FIX-002",
        "WATCH-003",
    ]
    assert len(results) == len(report.findings) <= 1000
    assert len(run["tool"]["driver"]["rules"]) <= 1000
    for result in results:
        assert result["ruleIndex"] == ["CFG-001", "FIX-002", "WATCH-003"].index(result["ruleId"])
        assert result["level"] in {"error", "warning", "note", "none"}
        assert result["message"]["text"]
        assert len(result["partialFingerprints"]["panopticon/v1"]) == 64
        for location in result.get("locations", ()):
            uri = location["physicalLocation"]["artifactLocation"]["uri"]
            assert not uri.startswith(("/", "\\", "../"))
            assert ".." not in uri
            assert len(uri) <= 4096
    assert results[0]["suppressions"][0]["status"] == "accepted"
    assert len(run["invocations"][0]["toolExecutionNotifications"]) == 2

    markdown = render_markdown(report)
    assert "| Rule | Severity | Finding | Location | State |" in markdown
    assert "Suppressed findings: 2" in markdown
    assert "Allowlist-excluded evidence: 2" in markdown
    assert "Evidence items: 7" in markdown
    assert "\\|" in markdown
    assert "\\<script\\>" in markdown
    assert "\\[click\\]\\(javascript:alert\\(1\\)\\)" in markdown
    assert "<script>" not in markdown
    assert "](" not in markdown
    assert SECRET not in markdown
    assert "Users/runner" not in markdown


def test_hostile_markdown_and_home_uri_are_escaped_or_rejected() -> None:
    report = _bundle()
    rendered = render(report, exit_code=7)
    sarif = json.loads(rendered.stdout)
    hostile = sarif["runs"][0]["results"][1]
    uri = hostile["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]

    assert rendered.stdout
    assert rendered.exit_code == 7
    assert uri == "unknown"
    assert SECRET not in rendered.stdout
    assert "Users/runner" not in rendered.stdout
    assert "<script>" not in rendered.stdout
    assert "javascript:" not in rendered.stdout
    assert "<script>" not in render_markdown(report)
    assert SECRET not in render_markdown(report)
    assert "Users/runner" not in render_markdown(report)
