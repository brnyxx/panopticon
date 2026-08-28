"""Deterministic, injectable doctor pipeline core."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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
    DoctorOutcome,
    DoctorRequest,
    RegistryLookup,
)
from panopticon.inventory.normalize import normalize_entries
from panopticon.registry.model import NormalizedHistory


@dataclass(frozen=True, slots=True)
class DoctorInputs:
    """Dependency injection boundary; adapters and lookups remain outside engine logic."""

    env: DiscoveryEnv
    adapters: Sequence[ClientAdapter] = ()
    registry_lookup: RegistryLookup | Mapping[str, NormalizedHistory] | None = None
    alerts: tuple[str, ...] = ()
    config_diagnostics: tuple[EngineDiagnostic, ...] = ()


class DoctorPlan(Protocol):
    def run(self, request: DoctorRequest) -> DoctorOutcome: ...


def run_doctor(request: DoctorRequest, inputs: DoctorInputs | None = None) -> DoctorOutcome:
    deps = inputs or DoctorInputs(DiscoveryEnv(Path.home(), Path.cwd(), "darwin"), ())
    adapters = tuple(deps.adapters) or registered_adapters(deps.env)
    selected = tuple(a for a in adapters if request.client is None or a.name == request.client)
    diagnostics = list(deps.config_diagnostics)
    clients: list[DoctorClient] = []
    successes = 0
    failures = 0
    for adapter in sorted(selected, key=lambda item: item.name):
        try:
            parsed = combine_results(discover(adapter, deps.env))
            if parsed.status is DiscoveryStatus.FOUND:
                servers = normalize_entries(
                    parsed.entries, client=adapter.name, home=str(deps.env.home)
                )
                histories: dict[str, NormalizedHistory] = {}
                for server in servers:
                    try:
                        if deps.registry_lookup is None:
                            value = None
                        elif callable(deps.registry_lookup):
                            value = deps.registry_lookup(server)
                        else:
                            value = deps.registry_lookup.get(str(server.installation_id))
                        if value is not None:
                            histories[str(server.installation_id)] = value
                    except (OSError, ValueError, TypeError, KeyError):
                        diagnostics.append(EngineDiagnostic("HISTORY_FAILED", adapter.name))
                clients.append(
                    DoctorClient(
                        adapter.name, parsed.status.value, group_installations(servers, histories)
                    )
                )
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
    data = DoctorData(clients=clients_tuple, alerts=tuple(sorted(set(deps.alerts))))
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
