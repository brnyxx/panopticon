from pathlib import Path

from panopticon.discovery import combine_results, discover
from panopticon.discovery.base import DiscoveryEnv, DiscoveryStatus
from panopticon.discovery.cursor import CursorAdapter
from panopticon.discovery.generic import GenericAdapter
from panopticon.discovery.vscode import VSCodeAdapter
from panopticon.discovery.windsurf import WindsurfAdapter


def test_project_candidates_are_cwd_plus_three_parents(tmp_path: Path) -> None:
    env = DiscoveryEnv(tmp_path / "home", tmp_path / "a/b/c/d", "linux")
    paths = CursorAdapter().candidate_paths(env)
    assert paths[:4] == [p / ".cursor/mcp.json" for p in (env.cwd, *env.cwd.parents[:3])]


def test_generic_extracts_both_supported_roots(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"mcpServers":{"a":{"command":"x"}},"servers":{"b":{"url":"http://x"}}}')
    env = DiscoveryEnv(tmp_path, tmp_path, "linux")
    result = combine_results(discover(GenericAdapter(path, env), env))
    assert result.status is DiscoveryStatus.FOUND
    assert [entry.name for entry in result.entries] == ["a", "b"]


def test_vscode_user_path_is_injected(tmp_path: Path) -> None:
    env = DiscoveryEnv(tmp_path, tmp_path, "windows", {"APPDATA": "C:/Users/u/AppData/Roaming"})
    assert VSCodeAdapter().candidate_paths(env)[-1] == Path(
        "C:/Users/u/AppData/Roaming/Code/User/settings.json"
    )


def test_windsurf_does_not_read_environment(tmp_path: Path) -> None:
    env = DiscoveryEnv(tmp_path, tmp_path, "linux", {"HOME": "/real"})
    assert WindsurfAdapter().candidate_paths(env) == [
        tmp_path / ".codeium/windsurf/mcp_config.json"
    ]
