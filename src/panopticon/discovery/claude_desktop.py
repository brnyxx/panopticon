"""Claude Desktop MCP configuration discovery."""

from __future__ import annotations

from pathlib import Path

from panopticon.discovery._config import ConfigReader, read_entries
from panopticon.discovery.base import (
    ClientAdapter,
    DiscoveryEnv,
    ParseResult,
    RawServerEntry,
)
from panopticon.models import ConfigScope


class ClaudeDesktopAdapter:
    name = "claude-desktop"

    def __init__(
        self,
        env: DiscoveryEnv | None = None,
        *,
        reader: ConfigReader | None = None,
    ) -> None:
        self._env = env
        self._reader = reader

    def candidate_paths(self, env: DiscoveryEnv) -> list[Path]:
        if env.os == "darwin":
            global_path = env.home / "Library/Application Support/Claude/claude_desktop_config.json"
        elif env.os == "windows":
            appdata = Path(env.env.get("APPDATA", str(env.home / "AppData/Roaming")))
            global_path = appdata / "Claude/claude_desktop_config.json"
        elif env.os == "linux":
            global_path = env.home / ".config/Claude/claude_desktop_config.json"
        else:
            raise ValueError(f"unsupported discovery OS: {env.os}")
        wsl_home = env.env.get("WSL_WINDOWS_HOME")
        if wsl_home is not None:
            return [
                global_path,
                Path(wsl_home) / "AppData/Roaming/Claude/claude_desktop_config.json",
            ]
        # Desktop has no project scope, but retaining this method's stable order
        # lets callers combine adapters uniformly.
        return [global_path]

    def parse(self, path: Path) -> ParseResult:
        home = self._env.home if self._env is not None else _home_for(path)
        return read_entries(
            path,
            home=home,
            scope=ConfigScope.GLOBAL,
            reader=self._reader,
        )

    def write(self, path: Path, entries: list[RawServerEntry]) -> None:
        raise PermissionError("DISCOVERY_READ_ONLY")


def _home_for(path: Path) -> Path:
    parts = path.parts
    if "Library" in parts:
        return Path(*parts[: parts.index("Library")])
    if ".config" in parts:
        return Path(*parts[: parts.index(".config")])
    if "AppData" in parts:
        return Path(*parts[: parts.index("AppData")])
    return path.parent


Adapter: type[ClientAdapter] = ClaudeDesktopAdapter
