"""Stable identities distinguish groups, installations, findings, and spans."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from panopticon.models import (
    ClientName,
    ConfigPath,
    ConfigScope,
    ContractViolationError,
    InstallationIdentityComponents,
    JsonPointer,
    derive_installation_id,
    derive_logical_key,
    derive_span_id,
    normalize_config_path,
)
from panopticon.models.ids import SpanIdValue


@pytest.mark.parametrize(
    ("path", "home"),
    [
        ("/Users/Alice/.cursor/mcp.json", "/Users/Alice"),
        ("/home/alice/.cursor/mcp.json", "/home/alice"),
        (r"C:\Users\Alice\.cursor\mcp.json", r"C:\Users\Alice"),
        ("/mnt/c/Users/Alice/.cursor/mcp.json", r"C:\Users\Alice"),
        (r"\\server\share\Users\Alice\.cursor\mcp.json", r"\\server\share\Users\Alice"),
        ("~/.cursor/mcp.json", "/Users/ignored"),
    ],
)
def test_path_forms_normalize_without_real_home(path: str, home: str) -> None:
    # Given / When: a supported native, drive, UNC, WSL, or home-relative path is normalized.
    normalized = normalize_config_path(path, home)

    # Then: only the stable home-relative form remains.
    assert normalized == "~/.cursor/mcp.json"
    assert home.casefold() not in normalized.casefold()


def test_duplicate_group_installs_keep_distinct_installation_ids() -> None:
    # Given: one group-level server appears under two client config entries.
    # When: installation identities are derived at entry grain.
    desktop = derive_installation_id(
        InstallationIdentityComponents(
            client=ClientName.CLAUDE_DESKTOP,
            config_path=ConfigPath("~/.config/claude.json"),
            scope=ConfigScope.GLOBAL,
            config_pointer=JsonPointer("/mcpServers/github"),
            entry_name="github",
        )
    )
    cursor = derive_installation_id(
        InstallationIdentityComponents(
            client=ClientName.CURSOR,
            config_path=ConfigPath("~/.cursor/mcp.json"),
            scope=ConfigScope.GLOBAL,
            config_pointer=JsonPointer("/mcpServers/github"),
            entry_name="github",
        )
    )

    # Then: duplicate server groups do not collide as installations.
    assert desktop != cursor
    assert str(desktop).startswith("inst_")


def test_identity_components_prevent_collisions() -> None:
    # Given: canonical installation, finding-subject, and tool-call components.
    first = derive_installation_id(
        InstallationIdentityComponents(
            client=ClientName.CURSOR,
            config_path=ConfigPath("~/.cursor/mcp.json"),
            scope=ConfigScope.GLOBAL,
            config_pointer=JsonPointer("/mcpServers/x"),
            entry_name="x",
        )
    )

    # When: one component changes and related identities are derived.
    second = derive_installation_id(
        InstallationIdentityComponents(
            client=ClientName.CURSOR,
            config_path=ConfigPath("~/.cursor/mcp.json"),
            scope=ConfigScope.GLOBAL,
            config_pointer=JsonPointer("/mcpServers/y"),
            entry_name="y",
        )
    )

    # Then: installation, logical, and span identities remain separate and stable.
    assert first != second
    assert derive_logical_key("WATCH-001", first, "api.example.com") == derive_logical_key(
        "WATCH-001", first, "api.example.com"
    )
    assert derive_logical_key("WATCH-001", first, "api.example.com") != derive_logical_key(
        "WATCH-001", first, "other.example.com"
    )
    first_span = derive_span_id("list_tools", 0)
    assert first_span == derive_span_id("list_tools", 0)
    assert first_span != derive_span_id("list_tools", 1)
    assert first_span != derive_span_id("other_tool", 0)
    assert TypeAdapter(SpanIdValue).validate_python(first_span) == first_span


def test_path_outside_home_and_traversal_are_rejected() -> None:
    # Given / When / Then: paths that cannot be safely normalized never become identity input.
    with pytest.raises(ContractViolationError):
        normalize_config_path("/tmp/client.json", "/Users/alice")
    with pytest.raises(ContractViolationError):
        normalize_config_path("~/../alice/client.json", "/Users/alice")
