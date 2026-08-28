"""Deterministic, injectable doctor pipeline core."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from panopticon.analyzers.config.catalog import FILESYSTEM_MCP_IDENTIFIERS
from panopticon.analyzers.config.entropy import token_classification
from panopticon.analyzers.config.model import ConfigInput
from panopticon.analyzers.config.rules import analyze as analyze_config
from panopticon.analyzers.history.rules import analyze_history
from panopticon.discovery import combine_results, discover, registered_adapters
from panopticon.discovery.base import ClientAdapter, DiscoveryEnv, DiscoveryStatus
from panopticon.engine.contracts import (
    CompleteResult,
    EngineDiagnostic,
    EngineReason,
    IncompleteResult,
    PartialResult,
    Result,
)
from panopticon.engine.doctor_grouping import group_installations
from panopticon.engine.doctor_model import (
    DoctorClient,
    DoctorData,
    DoctorHistoryOutcomes,
    DoctorOutcome,
    DoctorRequest,
)
from panopticon.inventory.normalize import normalize_entry
from panopticon.models.inventory import InstalledServer
from panopticon.registry.history import SnapshotSeries, append_snapshot
from panopticon.registry.model import NormalizedHistory
from panopticon.registry.provider import RegistryProvider, RegistryProviderResult


@dataclass(frozen=True, slots=True)
class DoctorInputs:
    """Dependency injection boundary; adapters and lookups remain outside engine logic."""

    env: DiscoveryEnv
    adapters: Sequence[ClientAdapter] = ()
    registry_lookup: RegistryProvider | None = None
    alerts: tuple[str, ...] = ()
    config_diagnostics: tuple[EngineDiagnostic, ...] = ()
    now: datetime | None = None

    def __post_init__(self) -> None:
        if self.now is not None and (self.now.tzinfo is None or self.now.utcoffset() is None):
            raise ValueError("doctor clock must be timezone-aware")


class DoctorPlan(Protocol):
    async def run(self, request: DoctorRequest) -> DoctorOutcome: ...


async def run_doctor(request: DoctorRequest, inputs: DoctorInputs | None = None) -> DoctorOutcome:
    deps = inputs or DoctorInputs(DiscoveryEnv(Path.home(), Path.cwd(), "darwin"), ())
    adapters = tuple(deps.adapters) or registered_adapters(deps.env)
    selected = tuple(a for a in adapters if request.client is None or a.name == request.client)
    diagnostics = list(deps.config_diagnostics)
    if request.client is not None and not selected:
        diagnostics.append(EngineDiagnostic("DISCOVERY_FAILED", request.client))
    clients: list[DoctorClient] = []
    all_servers: list[InstalledServer] = []
    env_values: dict[str, tuple[str, ...]] = {}
    allowed_paths: dict[str, tuple[str, ...]] = {}
    filesystem_servers: set[str] = set()
    token_header_keys: dict[str, tuple[str, ...]] = {}
    history_by_installation: dict[str, NormalizedHistory] = {}
    provider_series: dict[str, SnapshotSeries] = {}
    successes = 0
    failures = 0
    for adapter in sorted(selected, key=lambda item: item.name):
        try:
            parsed = combine_results(discover(adapter, deps.env))
            if parsed.status is DiscoveryStatus.FOUND:
                servers = tuple(
                    sorted(
                        (
                            normalize_entry(
                                entry,
                                client=adapter.name,
                                home=str(deps.env.home),
                            )
                            for entry in parsed.entries
                        ),
                        key=lambda item: str(item.installation_id),
                    )
                )
                all_servers.extend(servers)
                entries = {
                    str(
                        normalize_entry(
                            entry,
                            client=adapter.name,
                            home=str(deps.env.home),
                        ).installation_id
                    ): entry
                    for entry in parsed.entries
                }
                for server in servers:
                    installation_id = str(server.installation_id)
                    raw = entries[installation_id].raw
                    raw_env = raw.get("env")
                    if isinstance(raw_env, Mapping):
                        env_values[installation_id] = tuple(
                            str(raw_env[key])
                            for key in server.env_keys
                            if isinstance(raw_env.get(key), str)
                        )
                    allowed_paths[installation_id] = tuple(
                        argument
                        for argument in server.args
                        if argument.startswith(("/", "~", "$HOME"))
                        or (
                            len(argument) >= 3
                            and argument[0].isalpha()
                            and argument[1:3] in {":\\", ":/"}
                        )
                    )
                    classification = " ".join(
                        (
                            str(server.server_id),
                            server.name,
                            server.command or "",
                        )
                    ).casefold()
                    if any(
                        identifier in classification for identifier in FILESYSTEM_MCP_IDENTIFIERS
                    ):
                        filesystem_servers.add(installation_id)
                    raw_headers = raw.get("headers")
                    if isinstance(raw_headers, Mapping):
                        token_header_keys[installation_id] = tuple(
                            sorted(
                                str(key)
                                for key, value in raw_headers.items()
                                if isinstance(value, str)
                                and token_classification(value) is not None
                            )
                        )
                histories: dict[str, NormalizedHistory] = {}
                if not request.list_clients:
                    for server in sorted(servers, key=lambda item: str(item.installation_id)):
                        value = (
                            await deps.registry_lookup.lookup(server, request.offline)
                            if deps.registry_lookup is not None
                            else None
                        )
                        if isinstance(value, RegistryProviderResult):
                            diagnostics.extend(value.diagnostics)
                            provider_series[str(server.installation_id)] = value.series
                            if value.history is not None:
                                histories[str(server.installation_id)] = value.history
                clients.append(
                    DoctorClient(
                        adapter.name, parsed.status.value, group_installations(servers, histories)
                    )
                )
                history_by_installation.update(histories)
                successes += 1
            else:
                clients.append(DoctorClient(adapter.name, parsed.status.value))
                failures += 1
                if parsed.error is not None:
                    diagnostics.append(EngineDiagnostic("DISCOVERY_FAILED", adapter.name))
        except (OSError, ValueError, TypeError, KeyError):
            failures += 1
            diagnostics.append(EngineDiagnostic("ADAPTER_FAILED", adapter.name))
            clients.append(DoctorClient(adapter.name, "PARSE_ERROR"))
    clients_tuple = tuple(clients)
    config_matches = analyze_config(
        ConfigInput(
            servers=tuple(all_servers),
            env_values=env_values,
            allowed_paths=allowed_paths,
            filesystem_servers=frozenset(filesystem_servers),
            token_header_keys=token_header_keys,
        )
    )
    observed_at = deps.now or datetime.now(UTC)
    history_outcomes: list[DoctorHistoryOutcomes] = []
    for server in sorted(all_servers, key=lambda item: str(item.installation_id)):
        installation_id = str(server.installation_id)
        series = provider_series.get(installation_id, SnapshotSeries())
        current_history = history_by_installation.get(installation_id)
        if current_history is not None and (
            not series.snapshots or series.snapshots[-1].history != current_history
        ):
            series = append_snapshot(series, current_history, observed_at=observed_at)
        history_outcomes.append(
            DoctorHistoryOutcomes(
                installation_id,
                analyze_history(series, now=observed_at),
            )
        )
    data = DoctorData(
        clients=clients_tuple,
        alerts=tuple(sorted(set(deps.alerts))),
        config_matches=config_matches,
        history_outcomes=tuple(history_outcomes),
    )
    if request.list_clients and request.client is None and not request.fix:
        result: Result = CompleteResult(diagnostics=tuple(diagnostics))
    elif successes and failures:
        result = PartialResult(
            reason_code=EngineReason.PARTIAL_COVERAGE, diagnostics=tuple(diagnostics)
        )
    elif successes:
        result = CompleteResult(diagnostics=tuple(diagnostics))
    else:
        result = IncompleteResult(
            reason_code=EngineReason.DISCOVERY_FAILED, diagnostics=tuple(diagnostics)
        )
    return DoctorOutcome(result=result, data=data)


__all__ = ["DoctorInputs", "DoctorOutcome", "DoctorPlan", "DoctorRequest", "run_doctor"]
