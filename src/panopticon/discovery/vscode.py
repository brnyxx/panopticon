"""Visual Studio Code MCP configuration discovery."""

from __future__ import annotations

from pathlib import Path

from panopticon.discovery._config import ConfigReader, read_entries
from panopticon.discovery.base import ClientAdapter, DiscoveryEnv, ParseResult, RawServerEntry
from panopticon.models import ConfigScope
from panopticon.util.paths import order_candidate_paths, project_roots


class VSCodeAdapter:
    name = "vscode"

    def __init__(
        self,
        env: DiscoveryEnv | None = None,
        *,
        reader: ConfigReader | None = None,
    ) -> None:
        self._env = env
        self._reader = reader

    def candidate_paths(self, env: DiscoveryEnv) -> list[Path]:
        projects = [root / ".vscode/mcp.json" for root in project_roots(env.cwd)]
        if env.os == "darwin":
            user = env.home / "Library/Application Support/Code/User/settings.json"
        elif env.os == "windows":
            appdata = Path(env.env.get("APPDATA", str(env.home / "AppData/Roaming")))
            user = appdata / "Code/User/settings.json"
        elif env.os == "linux":
            user = env.home / ".config/Code/User/settings.json"
        else:
            raise ValueError(f"unsupported discovery OS: {env.os}")
        users = [user]
        wsl_home = env.env.get("WSL_WINDOWS_HOME")
        if wsl_home is not None:
            users.append(Path(wsl_home) / "AppData/Roaming/Code/User/settings.json")
        return list(order_candidate_paths(projects, users))

    def parse(self, path: Path) -> ParseResult:
        home = self._env.home if self._env else path.parent
        if path.name == "mcp.json" and ".vscode" in path.parts:
            return read_entries(
                path,
                home=home,
                scope=ConfigScope.PROJECT,
                pointers=("/servers", "/mcp.servers"),
                reader=self._reader,
            )
        return read_entries(
            path,
            home=home,
            scope=ConfigScope.GLOBAL,
            pointers=("/mcp/servers", "/mcp.servers", "/servers"),
            reader=self._reader,
        )

    def write(self, path: Path, entries: list[RawServerEntry]) -> None:
        raise PermissionError("DISCOVERY_READ_ONLY")


Adapter: type[ClientAdapter] = VSCodeAdapter
VsCodeAdapter = VSCodeAdapter
