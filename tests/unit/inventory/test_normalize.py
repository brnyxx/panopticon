from dataclasses import replace
from pathlib import Path

import pytest

from panopticon.discovery.base import RawServerEntry, SourceLocation
from panopticon.inventory.normalize import group_servers, normalize_entries, normalize_entry
from panopticon.inventory.parsers import normalize_url, parse_command, resolve_cached_version
from panopticon.models import ConfigPath, ConfigScope, JsonPointer
from panopticon.models.ids import ClientName
from panopticon.models.inventory import PackageEcosystem, PackageIdentity


def test_npx_scoped_prerelease_and_flags() -> None:
    parsed = parse_command(
        "npx", ("-y", "--package", "x", "@scope/server@1.2.3-beta", "--", "--port")
    )
    assert parsed.server_id == "npm:@scope/server"
    assert parsed.package is not None
    assert parsed.package.pinned == "1.2.3-beta"


def test_python_module_is_low_confidence_pypi_identity() -> None:
    parsed = parse_command("python", ("-m", "my_server"))
    assert parsed.server_id == "pypi:my-server"
    assert parsed.confidence == "low"


def test_url_redacts_credentials_query_and_default_port() -> None:
    assert (
        normalize_url("https://user:secret@Exämple.com:443/mcp?token=abc")
        == "https://xn--exmple-cua.com/mcp"
    )


def test_local_identity_is_deterministic() -> None:
    first = parse_command("custom", ("--flag", "value"))
    second = parse_command("custom", ("--flag", "value"))
    assert first.server_id == second.server_id
    assert first.confidence == "low"


@pytest.mark.parametrize(
    ("command", "args", "expected"),
    [
        ("npx", ("example-server",), "npm:example-server"),
        ("npx", ("-y", "example-server@1.0.0"), "npm:example-server"),
        ("npx", ("--yes", "@scope/server@2.0.0"), "npm:@scope/server"),
        ("npx", ("--package=helper", "@scope/server@2.0.0"), "npm:@scope/server"),
        ("npx", ("--package", "helper", "example-server"), "npm:example-server"),
        ("bunx", ("example-server",), "npm:example-server"),
        ("bunx.cmd", ("--bun", "example-server@next"), "npm:example-server"),
        ("node", ("/repo/node_modules/example-server/index.js",), "npm:example-server"),
        ("node", (r"C:\repo\node_modules\@scope\server\index.js",), "npm:@scope/server"),
        (
            "node",
            ("/repo/node_modules/@scope/example-server/dist/index.js",),
            "npm:@scope/example-server",
        ),
        ("uvx", ("python-server",), "pypi:python-server"),
        ("uvx", ("python-server@1.0.0",), "pypi:python-server"),
        ("uvx", ("--from", "python-server", "python-server-cli"), "pypi:python-server"),
        ("uvx", ("--from=python-server@1.2.0", "server"), "pypi:python-server"),
        ("pipx", ("run", "python-server@1.2.0"), "pypi:python-server"),
        ("python", ("-m", "python_server"), "pypi:python-server"),
        ("python3", ("-m", "package.module"), "pypi:package.module"),
        ("docker", ("run", "example/server"), "docker:example/server"),
        ("docker", ("run", "--rm", "example/server:1"), "docker:example/server:1"),
        (
            "docker",
            ("--context", "fixture", "run", "--network", "none", "example/server:1"),
            "docker:example/server:1",
        ),
        (
            "docker",
            ("run", "--network", "none", "example/server:2"),
            "docker:example/server:2",
        ),
        (
            "docker",
            ("run", "-e", "KEY=value", "example/server:3"),
            "docker:example/server:3",
        ),
        (
            "docker",
            ("run", "example/server@sha256:" + "a" * 64),
            "docker:example/server@sha256:" + "a" * 64,
        ),
        ("git-runner", ("https://github.com/Owner/Repo.git",), "github:owner/repo"),
        (
            "git-runner",
            ("git+https://github.com/Owner/Another.git#main",),
            "github:owner/another",
        ),
        ("", ("https://Example.com/mcp",), "remote:example.com/mcp"),
        ("", ("http://Example.com:80/mcp",), "remote:example.com/mcp"),
        ("custom", ("--flag",), "local:fd8fa3eb266f"),
        ("npx", ("${MCP_PACKAGE}",), "local:df47fc8b8c4d"),
        ("python", ("script.py",), "local:8206b08bd23d"),
    ],
)
def test_command_shapes_have_stable_group_identity(
    command: str,
    args: tuple[str, ...],
    expected: str,
) -> None:
    assert parse_command(command, args).server_id == expected


def test_unresolved_package_variable_remains_low_confidence() -> None:
    parsed = parse_command("npx", ("${MCP_PACKAGE}",))

    assert parsed.server_id.startswith("local:")
    assert parsed.confidence == "low"


def test_cache_resolution_reads_only_normalized_version(tmp_path: Path) -> None:
    metadata = tmp_path / ".npm/_npx/run/node_modules/@scope/server/package.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text('{"name":"@scope/server","version":"3.2.1","token":"synthetic"}')
    package = PackageIdentity(
        ecosystem=PackageEcosystem.NPM,
        name="@scope/server",
        pinned=None,
        resolved=None,
    )

    assert resolve_cached_version(package, tmp_path) == "3.2.1"


def test_normalize_entry_keeps_installation_identity_and_cache_version(tmp_path: Path) -> None:
    metadata = tmp_path / ".npm/_npx/run/node_modules/example-server/package.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text('{"version":"4.5.6"}')
    config_path = tmp_path / ".cursor/mcp.json"
    entry = RawServerEntry(
        name="fixture",
        raw={
            "command": "npx",
            "args": ["example-server@4"],
            "env": {"TOKEN": "synthetic-value"},
            "disabled": True,
        },
        scope=ConfigScope.GLOBAL,
        config_path=config_path,
        logical_path=ConfigPath("~/.cursor/mcp.json"),
        realpath=config_path,
        original_sha256="a" * 64,
        json_pointer=JsonPointer("/mcpServers/fixture"),
        source_location=SourceLocation(1, 1, 0),
    )

    installed = normalize_entry(entry, client=ClientName("cursor"), home=str(tmp_path))

    assert installed.server_id == "npm:example-server"
    assert installed.installation_id.startswith("inst_")
    assert installed.env_keys == ("TOKEN",)
    assert installed.disabled
    assert installed.package is not None
    assert installed.package.resolved == "4.5.6"


def test_duplicate_package_entries_group_without_merging(tmp_path: Path) -> None:
    config_path = tmp_path / ".cursor/mcp.json"
    first = RawServerEntry(
        name="first",
        raw={"command": "npx", "args": ["example-server"]},
        scope=ConfigScope.GLOBAL,
        config_path=config_path,
        logical_path=ConfigPath("~/.cursor/mcp.json"),
        realpath=config_path,
        original_sha256="a" * 64,
        json_pointer=JsonPointer("/mcpServers/first"),
        source_location=SourceLocation(1, 1, 0),
    )
    second = replace(
        first,
        name="second",
        json_pointer=JsonPointer("/mcpServers/second"),
    )

    servers = normalize_entries(
        [first, second],
        client=ClientName("cursor"),
        home=str(tmp_path),
    )
    groups = group_servers(servers)

    assert len(servers) == 2
    assert servers[0].installation_id != servers[1].installation_id
    assert len(groups) == 1
    assert groups[0].server_id == "npm:example-server"
    assert groups[0].installations == servers
