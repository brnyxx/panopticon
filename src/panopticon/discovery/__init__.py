"""Client config discovery and deterministic adapter registration."""

from __future__ import annotations

from pathlib import Path

from panopticon.discovery._config import ConfigReader
from panopticon.discovery.base import ClientAdapter, DiscoveryEnv, DiscoveryStatus, ParseResult
from panopticon.discovery.claude_code import ClaudeCodeAdapter
from panopticon.discovery.claude_desktop import ClaudeDesktopAdapter
from panopticon.discovery.cursor import CursorAdapter
from panopticon.discovery.generic import GenericAdapter
from panopticon.discovery.vscode import VSCodeAdapter
from panopticon.discovery.windsurf import WindsurfAdapter

CLIENT_NAMES = (
    "claude-desktop",
    "claude-code",
    "cursor",
    "vscode",
    "windsurf",
    "generic",
)


def registered_adapters(
    env: DiscoveryEnv,
    *,
    generic_config: Path | None = None,
    reader: ConfigReader | None = None,
) -> tuple[ClientAdapter, ...]:
    """Build every adapter from injected environment and read boundaries."""
    return (
        ClaudeDesktopAdapter(env, reader=reader),
        ClaudeCodeAdapter(env, reader=reader),
        CursorAdapter(env, reader=reader),
        VSCodeAdapter(env, reader=reader),
        WindsurfAdapter(env, reader=reader),
        GenericAdapter(generic_config, env, reader=reader),
    )


def discover(
    adapter: ClientAdapter,
    env: DiscoveryEnv,
) -> tuple[tuple[Path, ParseResult], ...]:
    """Read each deterministic candidate exactly once."""
    return tuple((path, adapter.parse(path)) for path in adapter.candidate_paths(env))


def combine_results(results: tuple[tuple[Path, ParseResult], ...]) -> ParseResult:
    """Combine per-path results without hiding partial adapter failures."""
    entries = [
        entry
        for _, result in results
        if result.status is DiscoveryStatus.FOUND
        for entry in result.entries
    ]
    if entries:
        return ParseResult(
            DiscoveryStatus.FOUND,
            entries=sorted(
                entries,
                key=lambda entry: (
                    entry.scope.value,
                    entry.config_path.as_posix(),
                    str(entry.json_pointer),
                ),
            ),
        )
    failure = next(
        (result for _, result in results if result.status is not DiscoveryStatus.NOT_FOUND),
        None,
    )
    return failure or ParseResult(DiscoveryStatus.NOT_FOUND)


__all__ = [
    "CLIENT_NAMES",
    "combine_results",
    "discover",
    "registered_adapters",
]
