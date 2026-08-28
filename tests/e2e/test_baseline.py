"""End-to-end baseline lifecycle through the Typer boundary."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from panopticon.cli.main import app


def test_baseline_create_list_show_remove(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    created = runner.invoke(app, ["baseline", "create", "--label", "first", "--json"])
    assert created.exit_code == 0
    created_payload = json.loads(created.stdout)
    baseline = created_payload["baselines"][0]
    baseline_id = baseline["baseline_id"]
    assert baseline["kind"] == "explicit"

    listed = runner.invoke(app, ["baseline", "list", "--json"])
    assert listed.exit_code == 0
    assert [item["baseline_id"] for item in json.loads(listed.stdout)["baselines"]] == [baseline_id]

    shown = runner.invoke(app, ["baseline", "show", baseline_id, "--json"])
    assert shown.exit_code == 0
    assert json.loads(shown.stdout)["baselines"][0]["baseline_id"] == baseline_id

    compared = runner.invoke(app, ["diff", "--since", baseline_id, "--json"])
    assert compared.exit_code == 0
    diff = json.loads(compared.stdout)["diff"]
    assert diff["meaningful"] == []
    assert diff["behavior"] == []
    assert diff["inventory"] == []

    removed = runner.invoke(app, ["baseline", "rm", baseline_id, "--json"])
    assert removed.exit_code == 0
    assert json.loads(removed.stdout)["removed"] == "REMOVED"
    missing = runner.invoke(app, ["baseline", "show", baseline_id, "--json"])
    assert missing.exit_code != 0
    assert "BASELINE_NOT_FOUND" in missing.stdout
