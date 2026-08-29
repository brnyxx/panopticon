from __future__ import annotations

import hashlib
import os
import platform
import re
from pathlib import Path

import json5
import pytest
from typer.testing import CliRunner

import panopticon.engine.fix as fix_engine
from panopticon.cli.main import app
from panopticon.discovery import discover, registered_adapters
from panopticon.discovery.base import DiscoveryEnv, DiscoveryStatus
from panopticon.engine.fix import FixCommandRequest, run_fix
from panopticon.fix.cli_model import FixOutcomeStatus


def _config_path(home: Path) -> Path:
    if platform.system() == "Darwin":
        return home / "Library/Application Support/Claude/claude_desktop_config.json"
    if platform.system() == "Windows":
        return home / "AppData/Roaming/Claude/claude_desktop_config.json"
    return home / ".config/Claude/claude_desktop_config.json"


def test_cli_dry_run_apply_undo_restores_hash(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    config = _config_path(home)
    config.parent.mkdir(parents=True)
    original = (
        b"// preserve this comment\n"
        b'{"mcpServers":{"disabled":{"command":"npx","args":["fixture@1.0.0"],'
        b'"disabled":true},"keep":{"command":"node","args":["server.js"]}}}\n'
    )
    config.write_bytes(original)
    original_hash = hashlib.sha256(original).hexdigest()
    monkeypatch.setenv("HOME", str(home))
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", str(home / "AppData/Roaming"))
    runner = CliRunner()
    arguments = [
        "fix",
        "disabled",
        "--rule",
        "FIX-010",
        "--client",
        "claude-desktop",
    ]

    dry_run = runner.invoke(app, [*arguments, "--dry-run"])
    assert dry_run.exit_code == 0
    assert config.read_bytes() == original
    assert "FIX-010 PLANNED PLAN_READY" in dry_run.stdout

    applied = runner.invoke(app, [*arguments, "--yes"])
    assert applied.exit_code == 0
    match = re.search(r"transaction=([0-9a-f]{20})", applied.stdout)
    assert match is not None
    changed = json5.loads(config.read_text())
    assert "disabled" not in changed["mcpServers"]
    assert changed["mcpServers"]["keep"]["args"] == ["server.js"]

    undone = runner.invoke(app, ["fix", "--undo", match.group(1)])
    assert undone.exit_code == 0
    assert hashlib.sha256(config.read_bytes()).hexdigest() == original_hash
    assert config.read_bytes() == original


def test_cli_offline_fix_008_never_constructs_transport(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    config = home / "generic.json"
    config.parent.mkdir()
    config.write_text(
        '{"mcpServers":{"remote":{"url":"http://example.test/mcp"}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))

    def unexpected_transport() -> None:
        raise AssertionError("offline fix constructed an outbound transport")

    monkeypatch.setattr(fix_engine, "HttpxTransport", unexpected_transport)
    result = CliRunner().invoke(
        app,
        [
            "fix",
            "remote",
            "--rule",
            "FIX-008",
            "--client",
            "generic",
            "--config",
            str(config),
            "--offline",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "FIX-008 GUIDANCE HTTPS_CHECK_UNAVAILABLE" in result.stdout
    assert "http://example.test/mcp" in config.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "client",
    ("claude-desktop", "claude-code", "cursor", "vscode", "windsurf", "generic"),
)
def test_all_client_disabled_fixtures_apply_and_undo_exactly(
    client: str,
    tmp_path: Path,
) -> None:
    case = tmp_path / client
    home = case / "home"
    cwd = home / "project"
    cwd.mkdir(parents=True)
    env = DiscoveryEnv(home, cwd, "darwin", {})
    fixture_client = client.replace("-", "_")
    source = (
        Path(__file__).parents[1] / "fixtures" / "discovery" / fixture_client / "disabled.json"
    ).read_bytes()
    generic = home / "generic.json" if client == "generic" else None
    adapters = registered_adapters(env, generic_config=generic)
    adapter = next(item for item in adapters if item.name == client)
    for candidate in adapter.candidate_paths(env):
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(source)
    entries = [
        entry
        for _path, result in discover(adapter, env)
        if result.status is DiscoveryStatus.FOUND
        for entry in result.entries
        if entry.raw.get("disabled") is True or entry.raw.get("enabled") is False
    ]
    assert entries
    target = entries[0].config_path
    original = target.read_bytes()
    request = FixCommandRequest(
        server=entries[0].name,
        rule="FIX-010",
        yes=True,
        client=client,
        config_path=generic,
    )
    applied = run_fix(request, env=env)
    assert applied.batch.outcomes[0].status is FixOutcomeStatus.RECHECKED
    transaction_id = applied.batch.outcomes[0].transaction_id
    assert transaction_id is not None
    undone = run_fix(
        FixCommandRequest(server=None, rule=None, undo=transaction_id),
        env=env,
    )
    assert undone.batch.outcomes[0].status is FixOutcomeStatus.UNDONE
    assert target.read_bytes() == original
