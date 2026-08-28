"""Windsurf MCP configuration discovery."""

from __future__ import annotations

from pathlib import Path

from panopticon.discovery._config import ConfigReader, read_entries
from panopticon.discovery.base import ClientAdapter, DiscoveryEnv, ParseResult, RawServerEntry
from panopticon.models import ConfigScope
from panopticon.util.paths import order_candidate_paths


class WindsurfAdapter:
    name = "windsurf"

    def __init__(
        self,
        env: DiscoveryEnv | None = None,
        *,
        reader: ConfigReader | None = None,
    ) -> None:
        self._env = env
        self._reader = reader

    def candidate_paths(self, env: DiscoveryEnv) -> list[Path]:
        if env.os == "windows":
            home = Path(env.env.get("USERPROFILE", str(env.home)))
        elif env.os in {"darwin", "linux"}:
            home = env.home
        else:
            raise ValueError(f"unsupported discovery OS: {env.os}")
        global_paths = [home / ".codeium/windsurf/mcp_config.json"]
        wsl_home = env.env.get("WSL_WINDOWS_HOME")
        if wsl_home is not None:
            global_paths.append(Path(wsl_home) / ".codeium/windsurf/mcp_config.json")
        return list(order_candidate_paths((), global_paths))

    def parse(self, path: Path) -> ParseResult:
        home = self._env.home if self._env else path.parent
        return read_entries(
            path,
            home=home,
            scope=ConfigScope.GLOBAL,
            pointers=("/mcpServers",),
            reader=self._reader,
        )

    def write(self, path: Path, entries: list[RawServerEntry]) -> None:
        raise PermissionError("DISCOVERY_READ_ONLY")


Adapter: type[ClientAdapter] = WindsurfAdapter
