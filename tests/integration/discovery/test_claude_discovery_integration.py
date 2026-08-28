from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from panopticon.discovery.base import DiscoveryEnv, DiscoveryStatus
from panopticon.discovery.claude_code import ClaudeCodeAdapter
from panopticon.discovery.claude_desktop import ClaudeDesktopAdapter

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "discovery"
VALID_FIXTURES = ("clean", "secret", "broad_fs", "duplicate", "disabled", "remote", "variables")


def test_list_clients_finds_exact_scopes(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "repo" / "service"
    cwd.mkdir(parents=True)
    desktop = home / ".config/Claude/claude_desktop_config.json"
    desktop.parent.mkdir(parents=True)
    desktop.write_text('{"mcpServers":{"desktop":{"command":"node"}}}')
    project = cwd / ".mcp.json"
    project.write_text('{"mcpServers":{"project":{"type":"http","url":"https://example.test"}}}')
    env = DiscoveryEnv(home, cwd, "linux")
    assert ClaudeDesktopAdapter(env).parse(desktop).entries[0].scope.value == "global"
    paths = ClaudeCodeAdapter(env).candidate_paths(env)
    assert paths[-1] == home / ".claude.json"
    assert project in paths
    assert ClaudeCodeAdapter(env).parse(project).entries[0].scope.value == "project"


def test_unreadable_and_malformed_configs_return_typed_status_without_write(tmp_path: Path) -> None:
    env = DiscoveryEnv(tmp_path, tmp_path, "linux")
    adapter = ClaudeDesktopAdapter(env)
    malformed = tmp_path / "config.json"
    malformed.write_bytes(b'{"mcpServers":')
    before = malformed.read_bytes()
    result = adapter.parse(malformed)
    assert result.status is DiscoveryStatus.PARSE_ERROR
    assert malformed.read_bytes() == before
    missing = adapter.parse(tmp_path / "missing.json")
    assert missing.status is DiscoveryStatus.NOT_FOUND


@pytest.mark.parametrize("client", ["claude_desktop", "claude_code"])
@pytest.mark.parametrize("fixture_name", VALID_FIXTURES)
def test_claude_fixture_matrix_is_read_only(
    tmp_path: Path,
    client: str,
    fixture_name: str,
) -> None:
    home = tmp_path / "home"
    source = FIXTURE_ROOT / client / f"{fixture_name}.json"
    path = (
        home / ".claude.json"
        if client == "claude_code"
        else home / ".config/Claude/claude_desktop_config.json"
    )
    path.parent.mkdir(parents=True)
    path.write_bytes(source.read_bytes())
    before = hashlib.sha256(path.read_bytes()).digest()
    env = DiscoveryEnv(home, tmp_path / "project", "linux")
    adapter = ClaudeCodeAdapter(env) if client == "claude_code" else ClaudeDesktopAdapter(env)

    result = adapter.parse(path)

    assert result.status is DiscoveryStatus.FOUND
    assert result.entries
    assert hashlib.sha256(path.read_bytes()).digest() == before
    assert all(entry.original_sha256 == before.hex() for entry in result.entries)


@pytest.mark.parametrize("client", ["claude_desktop", "claude_code"])
def test_claude_malformed_fixtures_return_parse_error(tmp_path: Path, client: str) -> None:
    home = tmp_path / "home"
    source = FIXTURE_ROOT / client / "malformed.json"
    path = home / (".claude.json" if client == "claude_code" else "desktop.json")
    path.parent.mkdir(parents=True)
    path.write_bytes(source.read_bytes())
    env = DiscoveryEnv(home, tmp_path / "project", "linux")
    adapter = ClaudeCodeAdapter(env) if client == "claude_code" else ClaudeDesktopAdapter(env)

    result = adapter.parse(path)

    assert result.status is DiscoveryStatus.PARSE_ERROR
    assert result.error is not None
    assert result.error.reason
