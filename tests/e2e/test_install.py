from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from panopticon.discovery.base import DiscoveryEnv
from panopticon.discovery.generic import GenericAdapter
from panopticon.engine.install import recheck_install
from panopticon.fix.executor import FixTransactionExecutor
from panopticon.install.model import InstallAction, InstallRequest, InstallStatus
from panopticon.install.service import execute
from panopticon.secrets.memory import InMemorySecretStore
from panopticon.store.repository import ArtifactRepository

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "discovery"
CLIENTS = (
    "claude-desktop",
    "claude-code",
    "cursor",
    "vscode",
    "windsurf",
    "generic",
)


def _env(tmp_path: Path) -> DiscoveryEnv:
    home = tmp_path / "home"
    cwd = tmp_path / "project"
    home.mkdir()
    cwd.mkdir()
    return DiscoveryEnv(home, cwd, "linux", {})


def _executor(tmp_path: Path) -> FixTransactionExecutor:
    return FixTransactionExecutor(
        ArtifactRepository((tmp_path / "store").resolve()),
        lambda: datetime(2026, 1, 1, tzinfo=UTC),
        secret_store=InMemorySecretStore(),
        rechecker=recheck_install,
    )


def _pano() -> str:
    name = "pano.exe" if os.name == "nt" else "pano"
    executable = Path(sys.executable).with_name(name)
    assert executable.is_file()
    return str(executable)


async def _launch(command: str, args: list[str], payload: bytes) -> tuple[int, bytes]:
    process = await asyncio.create_subprocess_exec(
        command,
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _stderr = await process.communicate(payload)
    return process.returncode or 0, stdout


def test_install_launch_uninstall_restores_original_hash(tmp_path: Path) -> None:
    env = _env(tmp_path)
    child = tmp_path / "relay.py"
    child.write_text(
        "import sys\n"
        "data=sys.stdin.buffer.read()\n"
        "sys.stdout.buffer.write(data)\n"
        "raise SystemExit(7)\n"
    )
    config = env.cwd / "generic.json"
    original = (
        b'{\n  // preserved\n  "mcpServers": {"demo": {"command": "'
        + sys.executable.encode()
        + b'", "args": ["'
        + str(child).encode()
        + b'"]}}\n}\n'
    )
    config.write_bytes(original)
    transaction = _executor(tmp_path)
    request = InstallRequest(
        "generic",
        config_path=config,
        dry_run=False,
        yes=True,
        pano_command=_pano(),
    )

    installed = execute(request, env, transaction=transaction)

    assert installed.successful
    assert installed.outcomes[0].status is InstallStatus.RECHECKED
    wrapped = GenericAdapter(config, env).parse(config).entries[0].raw
    command, args = wrapped["command"], wrapped["args"]
    assert isinstance(command, str) and isinstance(args, list)
    assert all(isinstance(argument, str) for argument in args)
    exit_code, stdout = asyncio.run(
        _launch(
            command,
            [argument for argument in args if isinstance(argument, str)],
            b"\x00mcp\xff",
        )
    )
    assert (exit_code, stdout) == (7, b"\x00mcp\xff")

    uninstalled = execute(
        InstallRequest(
            "generic",
            action=InstallAction.UNINSTALL,
            config_path=config,
            dry_run=False,
            yes=True,
            pano_command=_pano(),
        ),
        env,
        transaction=transaction,
    )

    assert uninstalled.successful
    assert config.read_bytes() == original


def _target(client: str, env: DiscoveryEnv) -> Path:
    return {
        "claude-desktop": env.home / ".config/Claude/claude_desktop_config.json",
        "claude-code": env.home / ".claude.json",
        "cursor": env.home / ".cursor/mcp.json",
        "vscode": env.home / ".config/Code/User/settings.json",
        "windsurf": env.home / ".codeium/windsurf/mcp_config.json",
        "generic": env.cwd / "generic.json",
    }[client]


@pytest.mark.parametrize("client", CLIENTS)
def test_every_client_fixture_install_uninstall_restores_exact_bytes(
    tmp_path: Path,
    client: str,
) -> None:
    env = _env(tmp_path)
    target = _target(client, env)
    target.parent.mkdir(parents=True, exist_ok=True)
    fixture_client = client.replace("-", "_")
    target.write_bytes((FIXTURES / fixture_client / "clean.json").read_bytes())
    original = target.read_bytes()
    generic = target if client == "generic" else None
    transaction = _executor(tmp_path)

    installed = execute(
        InstallRequest(
            client,
            config_path=generic,
            dry_run=False,
            yes=True,
            pano_command=_pano(),
        ),
        env,
        transaction=transaction,
    )
    assert installed.successful

    uninstalled = execute(
        InstallRequest(
            client,
            action=InstallAction.UNINSTALL,
            config_path=generic,
            dry_run=False,
            yes=True,
            pano_command=_pano(),
        ),
        env,
        transaction=transaction,
    )
    assert uninstalled.successful
    assert target.read_bytes() == original


def test_wrapped_remote_and_concurrent_entries_have_no_collateral_changes(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    config = env.cwd / "generic.json"
    original = (
        b'{"mcpServers":{"local":{"command":"node","args":["a"]},'
        b'"remote":{"url":"https://example.test"},'
        b'"disabled":{"command":"node","args":[],"disabled":true}}}'
    )
    config.write_bytes(original)
    transaction = _executor(tmp_path)
    planned = execute(
        InstallRequest(
            "generic",
            only="local",
            config_path=config,
            pano_command=_pano(),
        ),
        env,
        transaction=transaction,
    )
    assert planned.successful and config.read_bytes() == original

    plan = planned.outcomes[0].plan
    assert plan is not None
    config.write_bytes(original.replace(b'"a"', b'"edited"'))
    conflict = transaction.apply(plan.fix_plan, plan.selection, recheck=True)
    assert conflict.status.value == "CONFLICT"
    assert b'"edited"' in config.read_bytes()

    remote = execute(
        InstallRequest("generic", only="remote", config_path=config, pano_command=_pano()),
        env,
        transaction=transaction,
    )
    disabled = execute(
        InstallRequest("generic", only="disabled", config_path=config, pano_command=_pano()),
        env,
        transaction=transaction,
    )
    assert remote.outcomes[0].reason_code == "REMOTE_NOT_TARGET"
    assert disabled.outcomes[0].reason_code == "DISABLED"
