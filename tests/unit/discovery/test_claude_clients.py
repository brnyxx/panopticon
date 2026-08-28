from __future__ import annotations

from pathlib import Path

from panopticon.discovery.base import DiscoveryEnv, DiscoveryStatus
from panopticon.discovery.claude_code import ClaudeCodeAdapter
from panopticon.discovery.claude_desktop import ClaudeDesktopAdapter


class _DeniedReader:
    def read_bytes(self, path: Path) -> bytes:
        raise PermissionError(path)


def test_desktop_reads_jsonc_without_resolving_variables(tmp_path: Path) -> None:
    home = tmp_path / "home"
    path = home / "Library/Application Support/Claude/claude_desktop_config.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"mcpServers":{"z":{"command":"node","args":["${TOKEN}"]},"a":{"type":"http","url":"https://example.test"}}}'
    )
    adapter = ClaudeDesktopAdapter(DiscoveryEnv(home, tmp_path, "darwin"))
    result = adapter.parse(path)
    assert result.status is DiscoveryStatus.FOUND
    assert [entry.name for entry in result.entries] == ["a", "z"]
    assert result.entries[1].raw["args"] == ["${TOKEN}"]
    assert result.entries[0].json_pointer == "/mcpServers/a"


def test_code_reads_global_and_project_maps(tmp_path: Path) -> None:
    home = tmp_path / "home"
    path = home / ".claude.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"mcpServers":{"global":{"command":"x"}},"projects":{"/repo":{"mcpServers":{"local":{"type":"sse","url":"https://x"}}}}}'
    )
    result = ClaudeCodeAdapter(DiscoveryEnv(home, tmp_path, "linux")).parse(path)
    assert result.status is DiscoveryStatus.FOUND
    assert {entry.name for entry in result.entries} == {"global", "local"}
    assert any(entry.scope.value == "project" for entry in result.entries)


def test_missing_and_malformed_are_typed(tmp_path: Path) -> None:
    adapter = ClaudeCodeAdapter(DiscoveryEnv(tmp_path, tmp_path, "linux"))
    missing = adapter.parse(tmp_path / ".claude.json")
    assert missing.status is DiscoveryStatus.NOT_FOUND
    malformed_path = tmp_path / "bad.json"
    malformed_path.write_text('{"mcpServers":')
    malformed = adapter.parse(malformed_path)
    assert malformed.status is DiscoveryStatus.PARSE_ERROR
    assert malformed.error is not None and malformed.error.line is not None


def test_permission_failure_is_injected_and_typed(tmp_path: Path) -> None:
    path = tmp_path / ".claude.json"
    result = ClaudeCodeAdapter(
        DiscoveryEnv(tmp_path, tmp_path, "linux"),
        reader=_DeniedReader(),
    ).parse(path)

    assert result.status is DiscoveryStatus.PERMISSION
    assert result.error is not None
    assert result.error.reason == "PERMISSION"


def test_desktop_includes_injected_wsl_windows_config(tmp_path: Path) -> None:
    windows_home = tmp_path / "mnt/c/Users/Fixture"
    env = DiscoveryEnv(
        home=tmp_path / "home",
        cwd=tmp_path / "project",
        os="linux",
        env={"WSL_WINDOWS_HOME": str(windows_home)},
    )

    candidates = ClaudeDesktopAdapter(env).candidate_paths(env)

    assert candidates == [
        env.home / ".config/Claude/claude_desktop_config.json",
        windows_home / "AppData/Roaming/Claude/claude_desktop_config.json",
    ]
