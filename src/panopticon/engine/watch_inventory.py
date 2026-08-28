"""Read-only production inventory boundary for watch target selection."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path

from panopticon.discovery import combine_results, discover, registered_adapters
from panopticon.discovery.base import (
    ClientAdapter,
    DiscoveryEnv,
    DiscoveryStatus,
    RawServerEntry,
    SourceLocation,
)
from panopticon.inventory.normalize import normalize_entry
from panopticon.models.ids import ClientName, ConfigPath, ConfigScope, JsonPointer
from panopticon.models.inventory import InstalledServer

from .watch_model import TargetMode, TargetSelection
from .watch_self_metadata import acquire_self_metadata


class InventoryStatus(StrEnum):
    SELECTED = "SELECTED"
    MISSING = "MISSING"
    AMBIGUOUS = "AMBIGUOUS"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class WatchTargetContext:
    target: InstalledServer
    raw_entry: RawServerEntry = field(repr=False)

    @property
    def installed(self) -> InstalledServer:
        return self.target

    @property
    def entry(self) -> RawServerEntry:
        return self.raw_entry

    @property
    def name(self) -> str:
        return self.target.name


@dataclass(frozen=True, slots=True)
class InventorySelection:
    contexts: tuple[WatchTargetContext, ...] = ()
    status: InventoryStatus = InventoryStatus.SELECTED
    reason_code: str = "SELECTED"
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "contexts", tuple(self.contexts))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def __iter__(self) -> Iterator[WatchTargetContext]:
        return iter(self.contexts)


class ProductionWatchInventory:
    """Adapt registered discovery clients into deterministic, typed selections."""

    def __init__(
        self,
        env: DiscoveryEnv,
        *,
        adapters: Sequence[ClientAdapter] | None = None,
        self_command: (
            InstalledServer
            | WatchTargetContext
            | tuple[str, ...]
            | Callable[[], InstalledServer | WatchTargetContext | tuple[str, ...]]
            | None
        ) = None,
    ) -> None:
        self._env = env
        self._adapters = tuple(adapters) if adapters is not None else None
        self._self_command = self_command

    def _entries(self) -> tuple[tuple[tuple[RawServerEntry, str], ...], tuple[str, ...]]:
        adapters = self._adapters or registered_adapters(self._env)
        found: list[tuple[RawServerEntry, str]] = []
        diagnostics: list[str] = []
        for adapter in adapters:
            try:
                results = discover(adapter, self._env)
                combined = combine_results(results)
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                diagnostics.append(f"{adapter.name}:ADAPTER_FAILURE:{type(exc).__name__}")
                continue
            for _, result in results:
                if result.status in {DiscoveryStatus.NOT_FOUND, DiscoveryStatus.FOUND}:
                    continue
                detail = result.error.reason if result.error is not None else result.status.value
                diagnostics.append(f"{adapter.name}:{result.status.value}:{detail}")
            if combined.status is DiscoveryStatus.FOUND:
                found.extend((entry, adapter.name) for entry in combined.entries)
            elif combined.status is not DiscoveryStatus.NOT_FOUND:
                error = combined.error
                detail = error.reason if error is not None else combined.status.value
                if not any(
                    item.startswith(f"{adapter.name}:{combined.status.value}:")
                    for item in diagnostics
                ):
                    diagnostics.append(f"{adapter.name}:{combined.status.value}:{detail}")
        return tuple(found), tuple(diagnostics)

    def _context(self, entry: RawServerEntry, client: str) -> WatchTargetContext:
        if entry.scope is ConfigScope.PROJECT:
            acquired = acquire_self_metadata(self._env.cwd)
            entry = replace(
                entry,
                raw={**entry.raw, **acquired},
                metadata={**entry.metadata, **acquired},
            )
        return WatchTargetContext(
            normalize_entry(entry, client=client, home=str(self._env.home)), entry
        )

    def _self(self) -> InventorySelection:
        value = self._self_command
        if value is None:
            return InventorySelection(
                status=InventoryStatus.UNSUPPORTED, reason_code="SELF_UNSUPPORTED"
            )
        try:
            value = value() if callable(value) else value
            if isinstance(value, tuple):
                command = value
                if not command or not all(part for part in command):
                    raise ValueError("invalid self command")
                metadata = acquire_self_metadata(self._env.cwd)
                raw = RawServerEntry(
                    "self",
                    {
                        "command": command[0],
                        "args": list(command[1:]),
                        **metadata,
                    },
                    ConfigScope.PROJECT,
                    self._env.cwd,
                    ConfigPath("~"),
                    self._env.cwd,
                    "0" * 64,
                    JsonPointer("/self"),
                    SourceLocation(0, 0, 0),
                    metadata,
                )
                value = normalize_entry(raw, client=ClientName.GENERIC, home=str(self._env.home))
                context = WatchTargetContext(value, raw)
            elif isinstance(value, WatchTargetContext):
                context = value
            elif isinstance(value, InstalledServer):
                context = WatchTargetContext(value, _synthetic_entry(value, self._env))
            else:
                raise TypeError("invalid self target")
            return InventorySelection((context,), InventoryStatus.SELECTED, "SELF_EXPLICIT")
        except (TypeError, ValueError):
            return InventorySelection(
                status=InventoryStatus.UNSUPPORTED, reason_code="SELF_UNSUPPORTED"
            )

    def select(self, selection: TargetSelection) -> InventorySelection:
        if selection.mode is TargetMode.SELF:
            return self._self()
        entries, diagnostics = self._entries()
        contexts: list[WatchTargetContext] = []
        skipped: list[str] = []
        for entry, client in entries:
            installed = normalize_entry(entry, client=client, home=str(self._env.home))
            if installed.disabled:
                skipped.append(f"{client}:{entry.name}:DISABLED_SKIPPED")
                continue
            if (
                selection.mode is TargetMode.NAME and entry.name == selection.name
            ) or selection.mode is TargetMode.ALL:
                contexts.append(WatchTargetContext(installed, entry))
        contexts.sort(key=lambda context: str(context.target.installation_id))
        diagnostics = diagnostics + tuple(skipped)
        if selection.mode is TargetMode.NAME:
            if not contexts:
                return InventorySelection((), InventoryStatus.MISSING, "NAME_MISSING", diagnostics)
            if len(contexts) > 1:
                return InventorySelection(
                    (), InventoryStatus.AMBIGUOUS, "NAME_AMBIGUOUS", diagnostics
                )
        elif not contexts:
            return InventorySelection((), InventoryStatus.MISSING, "ALL_EMPTY", diagnostics)
        return InventorySelection(
            tuple(contexts), InventoryStatus.SELECTED, "SELECTED", diagnostics
        )


def _synthetic_entry(server: InstalledServer, env: DiscoveryEnv) -> RawServerEntry:
    return RawServerEntry(
        server.name,
        {"command": server.command or "", "args": list(server.args)},
        ConfigScope.PROJECT,
        Path(env.cwd),
        ConfigPath("~"),
        Path(env.cwd),
        "0" * 64,
        JsonPointer(""),
        SourceLocation(0, 0, 0),
    )


__all__ = [
    "InventorySelection",
    "InventoryStatus",
    "ProductionWatchInventory",
    "WatchTargetContext",
]
