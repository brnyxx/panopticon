from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal, assert_never

import pytest

from panopticon.discovery import CLIENT_NAMES, combine_results, discover, registered_adapters
from panopticon.discovery.base import ClientAdapter, DiscoveryEnv, DiscoveryStatus
from panopticon.discovery.cursor import CursorAdapter
from panopticon.discovery.generic import GenericAdapter
from panopticon.discovery.vscode import VSCodeAdapter
from panopticon.discovery.windsurf import WindsurfAdapter

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "discovery"
CLIENTS = ("cursor", "vscode", "windsurf", "generic")
VALID_FIXTURES = ("clean", "secret", "broad_fs", "duplicate", "disabled", "remote", "variables")
ClientName = Literal["cursor", "vscode", "windsurf", "generic"]


def _adapter(client: ClientName, env: DiscoveryEnv, path: Path) -> ClientAdapter:
    match client:
        case "cursor":
            return CursorAdapter(env)
        case "vscode":
            return VSCodeAdapter(env)
        case "windsurf":
            return WindsurfAdapter(env)
        case "generic":
            return GenericAdapter(path, env)
        case unreachable:
            assert_never(unreachable)


def _target(client: ClientName, env: DiscoveryEnv) -> Path:
    match client:
        case "cursor":
            return env.home / ".cursor/mcp.json"
        case "vscode":
            return env.home / ".config/Code/User/settings.json"
        case "windsurf":
            return env.home / ".codeium/windsurf/mcp_config.json"
        case "generic":
            return env.cwd / "generic.json"
        case unreachable:
            assert_never(unreachable)


def test_all_six_clients_are_registered_in_stable_order(tmp_path: Path) -> None:
    env = DiscoveryEnv(tmp_path / "home", tmp_path / "project", "linux")

    adapters = registered_adapters(env, generic_config=tmp_path / "generic.json")

    assert tuple(adapter.name for adapter in adapters) == CLIENT_NAMES


@pytest.mark.parametrize("client", CLIENTS)
@pytest.mark.parametrize("fixture_name", VALID_FIXTURES)
def test_remaining_fixture_matrix_is_read_only(
    tmp_path: Path,
    client: ClientName,
    fixture_name: str,
) -> None:
    env = DiscoveryEnv(tmp_path / "home", tmp_path / "project", "linux")
    target = _target(client, env)
    target.parent.mkdir(parents=True)
    target.write_bytes((FIXTURE_ROOT / client / f"{fixture_name}.json").read_bytes())
    before = hashlib.sha256(target.read_bytes()).digest()
    adapter = _adapter(client, env, target)

    result = combine_results(discover(adapter, env))

    assert result.status is DiscoveryStatus.FOUND
    assert result.entries
    assert hashlib.sha256(target.read_bytes()).digest() == before
    assert all(entry.original_sha256 == before.hex() for entry in result.entries)


@pytest.mark.parametrize("client", CLIENTS)
def test_remaining_malformed_fixtures_are_typed(tmp_path: Path, client: ClientName) -> None:
    env = DiscoveryEnv(tmp_path / "home", tmp_path / "project", "linux")
    target = _target(client, env)
    target.parent.mkdir(parents=True)
    target.write_bytes((FIXTURE_ROOT / client / "malformed.json").read_bytes())

    result = combine_results(discover(_adapter(client, env, target), env))

    assert result.status is DiscoveryStatus.PARSE_ERROR
    assert result.error is not None
    assert result.error.line is not None
