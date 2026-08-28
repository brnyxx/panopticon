from __future__ import annotations

from pathlib import Path

from panopticon.discovery.base import (
    DiscoveryEnv,
    DiscoveryStatus,
    ParseError,
    ParseResult,
    RawServerEntry,
    SourceLocation,
)
from panopticon.engine.watch_inventory import InventoryStatus, ProductionWatchInventory
from panopticon.engine.watch_model import TargetMode, TargetSelection
from panopticon.models import ConfigPath, ConfigScope, JsonPointer


class Adapter:
    def __init__(self, name: str, path: Path, result: ParseResult) -> None:
        self.name = name
        self.path = path
        self.result = result

    def candidate_paths(self, env: DiscoveryEnv) -> list[Path]:
        return [self.path]

    def parse(self, path: Path) -> ParseResult:
        return self.result

    def write(self, path: Path, entries: list[RawServerEntry]) -> None:
        raise AssertionError("watch inventory must remain read-only")


def _entry(
    path: Path,
    name: str,
    *,
    disabled: bool = False,
    scope: ConfigScope = ConfigScope.GLOBAL,
) -> RawServerEntry:
    return RawServerEntry(
        name,
        {
            "command": "npx",
            "args": [f"{name}@1.0.0"],
            "env": {"TOKEN": "synthetic-secret"},
            "disabled": disabled,
        },
        scope,
        path,
        ConfigPath(f"~/{path.name}"),
        path,
        "a" * 64,
        JsonPointer(f"/mcpServers/{name}"),
        SourceLocation(1, 1, 0),
    )


def _inventory(tmp_path: Path, *adapters: Adapter) -> ProductionWatchInventory:
    env = DiscoveryEnv(tmp_path, tmp_path, "darwin")
    return ProductionWatchInventory(env, adapters=adapters)


def test_name_and_all_are_deterministic_and_hide_raw_secrets(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    adapter = Adapter(
        "generic",
        path,
        ParseResult(DiscoveryStatus.FOUND, [_entry(path, "zeta"), _entry(path, "alpha")]),
    )
    inventory = _inventory(tmp_path, adapter)

    selected = inventory.select(TargetSelection(TargetMode.ALL))
    named = inventory.select(TargetSelection(TargetMode.NAME, "alpha"))

    assert selected.status is InventoryStatus.SELECTED
    installation_ids = [str(context.target.installation_id) for context in selected]
    assert installation_ids == sorted(installation_ids)
    assert {context.name for context in selected} == {"alpha", "zeta"}
    assert [context.name for context in named] == ["alpha"]
    assert "synthetic-secret" not in repr(selected)


def test_missing_ambiguous_disabled_and_parse_failure_are_visible(tmp_path: Path) -> None:
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = Adapter(
        "claude-code",
        first_path,
        ParseResult(
            DiscoveryStatus.FOUND,
            [_entry(first_path, "same"), _entry(first_path, "off", disabled=True)],
        ),
    )
    second = Adapter(
        "cursor", second_path, ParseResult(DiscoveryStatus.FOUND, [_entry(second_path, "same")])
    )
    broken = Adapter(
        "windsurf",
        tmp_path / "broken.json",
        ParseResult(
            DiscoveryStatus.PARSE_ERROR,
            error=ParseError(tmp_path / "broken.json", "INVALID_JSON"),
        ),
    )
    inventory = _inventory(tmp_path, first, second, broken)

    ambiguous = inventory.select(TargetSelection(TargetMode.NAME, "same"))
    missing = inventory.select(TargetSelection(TargetMode.NAME, "off"))

    assert ambiguous.status is InventoryStatus.AMBIGUOUS
    assert missing.status is InventoryStatus.MISSING
    assert any("DISABLED_SKIPPED" in item for item in missing.diagnostics)
    assert any("PARSE_ERROR:INVALID_JSON" in item for item in missing.diagnostics)
    assert all(str(tmp_path) not in item for item in missing.diagnostics)


def test_self_requires_explicit_command(tmp_path: Path) -> None:
    env = DiscoveryEnv(tmp_path, tmp_path, "darwin")
    unsupported = ProductionWatchInventory(env).select(TargetSelection(TargetMode.SELF))
    explicit = ProductionWatchInventory(env, self_command=("python", "server.py")).select(
        TargetSelection(TargetMode.SELF)
    )

    assert unsupported.status is InventoryStatus.UNSUPPORTED
    assert unsupported.reason_code == "SELF_UNSUPPORTED"
    assert explicit.status is InventoryStatus.SELECTED
    assert explicit.contexts[0].target.command == "python"
    assert explicit.contexts[0].target.args == ("server.py",)


def test_project_named_target_acquires_declaration_metadata(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("Reads ~/project only.", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    path = tmp_path / "mcp.json"
    adapter = Adapter(
        "generic",
        path,
        ParseResult(
            DiscoveryStatus.FOUND,
            [_entry(path, "project", scope=ConfigScope.PROJECT)],
        ),
    )

    selected = _inventory(tmp_path, adapter).select(TargetSelection(TargetMode.NAME, "project"))

    assert selected.status is InventoryStatus.SELECTED
    assert selected.contexts[0].raw_entry.raw["readme"] == "Reads ~/project only."
    assert selected.contexts[0].raw_entry.raw["manifest"] == {"name": "fixture"}
