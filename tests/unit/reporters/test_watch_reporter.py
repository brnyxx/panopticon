"""Watch-specific rendering acceptance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from panopticon.engine.contracts import (
    CompleteResult,
    EngineDiagnostic,
    FailedResult,
    PartialResult,
)
from panopticon.engine.watch_service import WatchServiceOutcome
from panopticon.engine.watch_service_targets import WatchTargetReceipt
from panopticon.reporters.watch import from_outcome, render


def _outcome(*targets: WatchTargetReceipt, result=None) -> WatchServiceOutcome:
    return WatchServiceOutcome(result or CompleteResult(), tuple(targets))


def test_from_outcome_converts_and_sorts_sanitized_target_data() -> None:
    outcome = _outcome(
        WatchTargetReceipt(
            name="zeta",
            status="PARTIAL",
            reason_code="PARTIAL_COVERAGE",
            observation_path="artifacts/zeta.json",
            observation_count=2,
            evidence_count=7,
            finding_count=2,
            suppression_count=1,
            excluded_allowlist_count=3,
            findings=(
                ("WATCH-002", "LOW", "second", False),
                ("WATCH-001", "HIGH", "first", True),
            ),
            coverage=(("net", "COMPLETE", "OK"), ("file", "UNKNOWN", "MISSING")),
        ),
        WatchTargetReceipt("alpha", "COMPLETE", "COMPLETED"),
        result=PartialResult(diagnostics=(EngineDiagnostic("WATCH_NOTE", "sanitized diagnostic"),)),
    )

    model = from_outcome(outcome)

    assert model.status == "PARTIAL"
    assert model.reason_code == "PARTIAL_COVERAGE"
    assert [target.name for target in model.targets] == ["alpha", "zeta"]
    target = model.targets[1]
    assert target.observation_count == 2
    assert target.evidence_count == 7
    assert target.finding_count == 2
    assert target.suppression_count == 1
    assert target.excluded_allowlist_count == 3
    assert target.findings == (
        ("WATCH-001", "HIGH", "first", True),
        ("WATCH-002", "LOW", "second", False),
    )
    assert target.coverage == (("file", "UNKNOWN", "MISSING"), ("net", "COMPLETE", "OK"))
    assert model.diagnostics == (("WATCH_NOTE", "sanitized diagnostic"),)


def test_render_terminal_is_deterministic_and_reports_counts_findings_and_coverage() -> None:
    outcome = _outcome(
        WatchTargetReceipt(
            "target",
            "PARTIAL",
            "PARTIAL_COVERAGE",
            "observations/target.json",
            1,
            4,
            1,
            1,
            2,
            (("WATCH-003", "HIGH", "unsafe behavior", True),),
            (("net", "UNSUPPORTED", "NO_PROXY"),),
        ),
        result=PartialResult(diagnostics=(EngineDiagnostic("NOTE", "detail"),)),
    )

    first = render(outcome, json_output=False)
    second = render(outcome, json_output=False)

    assert first == second
    assert first.stderr == ""
    assert first.exit_code == 0
    for text in (
        "Status: PARTIAL",
        "Reason: PARTIAL_COVERAGE",
        "Target: target",
        "Observations: 1",
        "Evidence: 4",
        "Findings: 1",
        "Suppressed: 1",
        "Allowlist-excluded: 2",
        "WATCH-003 HIGH: unsafe behavior [SUPPRESSED]",
        "net: UNSUPPORTED (NO_PROXY)",
        "Diagnostics: NOTE",
    ):
        assert text in first.stdout


def test_render_json_is_canonical_and_preserves_empty_unknown_target() -> None:
    outcome = _outcome(
        WatchTargetReceipt("unknown", "INCOMPLETE", "TIMEOUT"),
        WatchTargetReceipt("empty", "COMPLETE", "COMPLETED"),
        result=CompleteResult(),
    )

    first = render(outcome, json_output=True)
    second = render(outcome, json_output=True)

    assert first == second
    assert first.stderr == ""
    payload = json.loads(first.stdout)
    assert payload["status"] == "COMPLETE"
    assert [target["name"] for target in payload["targets"]] == ["empty", "unknown"]
    unknown = payload["targets"][1]
    assert unknown["artifact_path"] is None
    assert unknown["observation_count"] == 0
    assert unknown["findings"] == []
    assert [stage["name"] for stage in unknown["coverage"]] == [
        "dns",
        "file",
        "net",
        "process",
        "proxy",
        "snapshot",
        "stdio",
    ]
    assert all(stage["status"] == "UNKNOWN" for stage in unknown["coverage"])
    assert payload["diagnostics"] == []


def test_hostile_secret_and_home_values_are_rejected_before_emission() -> None:
    secret = "ghp_abcdefghijklmnopqrstuvwxyz123456"
    for detail in (secret, str(Path.home() / "private.json")):
        outcome = _outcome(
            result=FailedResult(diagnostics=(EngineDiagnostic("PROHIBITED_INPUT", detail),))
        )
        terminal = render(outcome, json_output=False)
        machine = render(outcome, json_output=True)
        assert terminal.stdout == ""
        assert machine.stdout == ""
        assert terminal.stderr == machine.stderr == ""
        assert terminal.exit_code == machine.exit_code == 1


def test_from_outcome_rejects_home_value_directly() -> None:
    outcome = _outcome(
        result=FailedResult(
            diagnostics=(EngineDiagnostic("PROHIBITED_INPUT", str(Path.home() / "secret.txt")),)
        )
    )
    with pytest.raises(ValueError, match="prohibited evidence"):
        from_outcome(outcome)
