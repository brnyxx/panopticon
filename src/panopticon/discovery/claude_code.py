"""Claude Code MCP configuration discovery."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from panopticon.discovery._config import (
    ConfigReader,
    FileConfigReader,
    logical_path,
    read_entries,
)
from panopticon.discovery.base import (
    ClientAdapter,
    DiscoveryEnv,
    DiscoveryStatus,
    ParseError,
    ParseResult,
    RawServerEntry,
)
from panopticon.models import ConfigPath, ConfigScope
from panopticon.util.jsonc.parser import JsoncParseError, parse_document
from panopticon.util.paths import order_candidate_paths, project_roots


class ClaudeCodeAdapter:
    name = "claude-code"

    def __init__(
        self,
        env: DiscoveryEnv | None = None,
        *,
        reader: ConfigReader | None = None,
    ) -> None:
        self._env = env
        self._reader = reader

    def candidate_paths(self, env: DiscoveryEnv) -> list[Path]:
        global_path = env.home / ".claude.json"
        projects = [root / ".mcp.json" for root in project_roots(env.cwd)]
        return list(order_candidate_paths(projects, (global_path,)))

    def parse(self, path: Path) -> ParseResult:
        home = self._env.home if self._env is not None else _home_for(path)
        if path.name == ".mcp.json":
            return read_entries(
                path,
                home=home,
                scope=ConfigScope.PROJECT,
                reader=self._reader,
            )
        # The global file contains both global servers and a project map.
        result = read_entries(
            path,
            home=home,
            scope=ConfigScope.GLOBAL,
            reader=self._reader,
        )
        if result.status is not DiscoveryStatus.FOUND:
            return result
        project_pointers: list[str] = []
        try:
            document = parse_document(
                (self._reader or FileConfigReader()).read_bytes(path),
                path=path,
                logical_path=result.entries[0].logical_path
                if result.entries
                else _logical(path, home),
            )
            value = document.value
            if isinstance(value, Mapping) and isinstance(value.get("projects"), Mapping):
                projects = value["projects"]
                assert isinstance(projects, Mapping)
                for project in sorted(key for key in projects if isinstance(key, str)):
                    project_pointers.append(f"/projects/{_escape(project)}/mcpServers")
        except (OSError, ValueError, JsoncParseError) as error:
            if isinstance(error, JsoncParseError):
                return ParseResult(
                    DiscoveryStatus.PARSE_ERROR,
                    error=ParseError(path, error.code, error.line, error.column, error.offset),
                )
            project_pointers = []
        if project_pointers:
            project_result = read_entries(
                path,
                home=home,
                scope=ConfigScope.PROJECT,
                pointers=project_pointers,
                reader=self._reader,
            )
            result.entries.extend(project_result.entries)
        return ParseResult(
            result.status, sorted(result.entries, key=lambda e: str(e.json_pointer)), result.error
        )

    def write(self, path: Path, entries: list[RawServerEntry]) -> None:
        raise PermissionError("DISCOVERY_READ_ONLY")


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _home_for(path: Path) -> Path:
    return path.parent


def _logical(path: Path, home: Path) -> ConfigPath:
    return logical_path(path, home)


Adapter: type[ClientAdapter] = ClaudeCodeAdapter
