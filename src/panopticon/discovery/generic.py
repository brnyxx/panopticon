"""Discovery adapter for an explicitly supplied MCP configuration."""

from __future__ import annotations

from pathlib import Path

from panopticon.discovery._config import ConfigReader, read_entries
from panopticon.discovery.base import ClientAdapter, DiscoveryEnv, ParseResult, RawServerEntry
from panopticon.models import ConfigScope


class GenericAdapter:
    name = "generic"

    def __init__(
        self,
        config_path: Path | str | None = None,
        env: DiscoveryEnv | None = None,
        *,
        reader: ConfigReader | None = None,
    ) -> None:
        self.config_path = Path(config_path) if config_path is not None else None
        self._env = env
        self._reader = reader

    def candidate_paths(self, env: DiscoveryEnv) -> list[Path]:
        return [self.config_path] if self.config_path is not None else []

    def parse(self, path: Path) -> ParseResult:
        home = self._env.home if self._env else path.parent
        return read_entries(
            path,
            home=home,
            scope=ConfigScope.GLOBAL,
            pointers=("/mcpServers", "/servers"),
            reader=self._reader,
        )

    def write(self, path: Path, entries: list[RawServerEntry]) -> None:
        raise PermissionError("DISCOVERY_READ_ONLY")


Adapter: type[ClientAdapter] = GenericAdapter
