"""Cursor MCP configuration discovery."""

from __future__ import annotations

from pathlib import Path

from panopticon.discovery._config import ConfigReader, read_entries
from panopticon.discovery.base import ClientAdapter, DiscoveryEnv, ParseResult, RawServerEntry
from panopticon.models import ConfigScope
from panopticon.util.paths import order_candidate_paths, project_roots


class CursorAdapter:
    name = "cursor"

    def __init__(
        self,
        env: DiscoveryEnv | None = None,
        *,
        reader: ConfigReader | None = None,
    ) -> None:
        self._env = env
        self._reader = reader

    def candidate_paths(self, env: DiscoveryEnv) -> list[Path]:
        projects = [root / ".cursor/mcp.json" for root in project_roots(env.cwd)]
        if env.os == "windows":
            profile = Path(env.env.get("USERPROFILE", str(env.home)))
            global_paths = [profile / ".cursor/mcp.json"]
        elif env.os in {"darwin", "linux"}:
            global_paths = [env.home / ".cursor/mcp.json"]
        else:
            raise ValueError(f"unsupported discovery OS: {env.os}")
        wsl_home = env.env.get("WSL_WINDOWS_HOME")
        if wsl_home is not None:
            global_paths.append(Path(wsl_home) / ".cursor/mcp.json")
        return list(order_candidate_paths(projects, global_paths))

    def parse(self, path: Path) -> ParseResult:
        home = self._env.home if self._env else path.parent
        project_paths = (
            {root / ".cursor/mcp.json" for root in project_roots(self._env.cwd)}
            if self._env is not None
            else set()
        )
        scope = ConfigScope.PROJECT if path in project_paths else ConfigScope.GLOBAL
        return read_entries(
            path,
            home=home,
            scope=scope,
            pointers=("/mcpServers",),
            reader=self._reader,
        )

    def write(self, path: Path, entries: list[RawServerEntry]) -> None:
        raise PermissionError("DISCOVERY_READ_ONLY")


Adapter: type[ClientAdapter] = CursorAdapter
