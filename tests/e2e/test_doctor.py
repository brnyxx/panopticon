"""End-to-end coverage for the real doctor Typer boundary."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from panopticon.cli.main import app


def _home(monkeypatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)
    return home


def test_doctor_and_list_clients_in_isolated_home(monkeypatch, tmp_path: Path) -> None:
    home = _home(monkeypatch, tmp_path)
    config = home / ".claude.json"
    config.write_text(
        '{"mcpServers":{"zeta":{"command":"node","args":["server.js"],'
        '"env":{"TOKEN":"secret"}},"alpha":{"url":"HTTPS://EXAMPLE.TEST/"}}}',
        encoding="utf-8",
    )
    before = config.read_bytes()
    runner = CliRunner()
    listed = runner.invoke(app, ["doctor", "--list-clients", "--offline"])
    assert listed.exit_code == 0
    assert "claude-code: FOUND" in listed.stdout
    rendered = runner.invoke(app, ["doctor", "--json", "--offline", "--client", "claude-code"])
    assert rendered.exit_code == 0
    payload = json.loads(rendered.stdout)
    clients = payload["doctor"]["clients"]
    claude = next(item for item in clients if item["name"] == "claude-code")
    group_ids = [group["server_id"] for group in claude["groups"]]
    assert group_ids == sorted(group_ids)
    for group in claude["groups"]:
        ids = [item["installation_id"] for item in group["installations"]]
        assert ids == sorted(ids)
    assert "secret" not in rendered.stdout
    assert config.read_bytes() == before


def test_malformed_client_preserves_other_results_and_partial_exit(
    monkeypatch, tmp_path: Path
) -> None:
    home = _home(monkeypatch, tmp_path)
    good = home / ".claude.json"
    good.write_text('{"mcpServers":{"ok":{"command":"node"}}}', encoding="utf-8")
    bad = home / ".cursor" / "mcp.json"
    bad.parent.mkdir()
    bad.write_text("{ malformed", encoding="utf-8")
    good_before, bad_before = good.read_bytes(), bad.read_bytes()
    rendered = CliRunner().invoke(app, ["doctor", "--json", "--offline"])
    assert rendered.exit_code == 3
    payload = json.loads(rendered.stdout)
    clients = {item["name"]: item for item in payload["doctor"]["clients"]}
    assert clients["claude-code"]["status"] == "FOUND"
    assert clients["cursor"]["status"] == "PARSE_ERROR"
    assert payload["status"] == "PARTIAL"
    assert payload["diagnostics"]
    assert good.read_bytes() == good_before
    assert bad.read_bytes() == bad_before
