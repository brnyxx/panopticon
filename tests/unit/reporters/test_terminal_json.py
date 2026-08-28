from __future__ import annotations

import json
from pathlib import Path

from panopticon.engine.contracts import EngineDiagnostic, FailedResult
from panopticon.reporters.base import Reporter
from panopticon.reporters.foundation import render as render_result
from panopticon.reporters.json import JsonReporter
from panopticon.reporters.json import render_model as render_json
from panopticon.reporters.model import DiagnosticView, SanitizedRenderModel, StageView
from panopticon.reporters.terminal import TerminalReporter
from panopticon.reporters.terminal import render_model as render_terminal


def mixed_model() -> SanitizedRenderModel:
    return SanitizedRenderModel(
        status="PARTIAL",
        reason_code="PARTIAL_COVERAGE",
        stages=(
            StageView("proxy", "UNSUPPORTED", "ROOTLESS_ATTRIBUTION_PARTIAL"),
            StageView("file", "COMPLETE", "OK"),
            StageView(
                "dns",
                "UNKNOWN",
                "SOURCE_MISSING",
                (DiagnosticView("DNS_LOG_MISSING", "DNS log was unavailable."),),
            ),
        ),
        diagnostics=(DiagnosticView("PIPELINE_PARTIAL", "One source was incomplete."),),
        evidence_count=4,
        excluded_allowlist_count=2,
        suppression_count=1,
    )


def test_mixed_coverage_renders_terminal_and_json() -> None:
    model = mixed_model()

    first = render_json(model)
    second = render_json(model)
    payload = json.loads(first.stdout)
    terminal = render_terminal(model, locale="en")

    assert first == second
    assert [row["name"] for row in payload["coverage"]] == ["dns", "file", "proxy"]
    assert {row["status"] for row in payload["coverage"]} == {
        "COMPLETE",
        "UNKNOWN",
        "UNSUPPORTED",
    }
    assert payload["excluded_allowlist_count"] == 2
    assert payload["suppression_count"] == 1
    assert terminal.stderr == ""
    assert terminal.stdout.index("dns:") < terminal.stdout.index("file:")
    assert terminal.stdout.index("file:") < terminal.stdout.index("proxy:")


def test_tty_and_locale_change_labels_not_machine_values() -> None:
    model = mixed_model()

    plain = render_terminal(model, tty=False, locale="ko")
    tty = render_terminal(model, tty=True, locale="ko")

    assert "PARTIAL" in plain.stdout
    assert "UNKNOWN" in plain.stdout
    assert "\x1b[1m" not in plain.stdout
    assert tty.stdout.startswith("\x1b[1m")
    assert tty.stdout.endswith("\x1b[0m")


def test_empty_and_failure_states_remain_explicit() -> None:
    model = SanitizedRenderModel(status="FAILED", reason_code="STAGE_ERROR")

    terminal = render_terminal(model)
    payload = json.loads(render_json(model).stdout)

    assert "FAILED" in terminal.stdout
    assert "STAGE_ERROR" in terminal.stdout
    assert payload["coverage"] == []
    assert payload["status"] == "FAILED"


def test_secret_evidence_is_rejected_before_emission() -> None:
    result = FailedResult(
        diagnostics=(
            EngineDiagnostic(
                "PROHIBITED_INPUT",
                str(Path.home() / "private-token"),
            ),
        )
    )

    output = render_result(result, json_output=False)

    assert output.stdout == ""
    assert output.stderr == ""
    assert output.exit_code != 0


def test_reporter_protocol_accepts_only_sanitized_models() -> None:
    reporters: tuple[Reporter, ...] = (JsonReporter(), TerminalReporter())

    for reporter in reporters:
        assert reporter.render(mixed_model()).stdout
