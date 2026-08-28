from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from panopticon.cli.main import app

FIXTURE = Path(__file__).parents[1] / "fixtures" / "schemas" / "observation.json"


def _eligible_payload() -> dict[str, object]:
    payload: Any = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["declared"]["completeness"] = "COMPLETE"
    state = payload["state"]
    state["overall"] = {"status": "COMPLETE", "reason_code": "COMPLETED", "diagnostics": []}
    for name in state["stages"]:
        if name == "handshake":
            state["stages"][name] = {
                "status": "NOT_REQUESTED",
                "reason_code": "MODERN_HANDSHAKE_NOT_REQUESTED",
                "diagnostics": [],
            }
        else:
            state["stages"][name] = {
                "status": "COMPLETE",
                "reason_code": "VERSION_SELECTED" if name == "version_discovery" else "COMPLETED",
                "diagnostics": [],
            }
    for name in state["coverage"]:
        state["coverage"][name] = {
            "status": "COMPLETE",
            "reason_code": "COMPLETED",
            "diagnostics": [],
        }
    payload["findings"] = []
    payload["spans"] = []
    return dict(payload)


def test_badge_writes_deterministic_accessible_svg_through_cli(tmp_path: Path) -> None:
    source = tmp_path / "observation.json"
    payload = _eligible_payload()
    observed_on = str(payload["observed_at"])[:10]
    source.write_text(json.dumps(payload), encoding="utf-8")
    first = tmp_path / "first.svg"
    second = tmp_path / "second.svg"
    runner = CliRunner()

    first_result = runner.invoke(app, ["badge", str(source), "--output", str(first)])
    second_result = runner.invoke(app, ["badge", str(source), "--output", str(second)])

    assert first_result.exit_code == second_result.exit_code == 0
    assert first.read_bytes() == second.read_bytes()
    rendered = first.read_text(encoding="utf-8")
    assert 'role="img"' in rendered
    assert observed_on in rendered


def test_badge_denies_incomplete_and_missing_observations(tmp_path: Path) -> None:
    incomplete = tmp_path / "incomplete.json"
    incomplete.write_bytes(FIXTURE.read_bytes())
    denied = tmp_path / "denied.svg"
    runner = CliRunner()

    partial = runner.invoke(app, ["badge", str(incomplete), "--output", str(denied)])
    missing = runner.invoke(
        app,
        ["badge", str(tmp_path / "missing.json"), "--output", str(tmp_path / "missing.svg")],
    )

    assert partial.exit_code != 0
    assert "BADGE_INELIGIBLE" in partial.stderr
    assert not denied.exists()
    assert missing.exit_code != 0
    assert not (tmp_path / "missing.svg").exists()
