"""Typed, sanitized doctor pipeline models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from panopticon.discovery.base import ClientAdapter, DiscoveryEnv
from panopticon.engine.contracts import EngineDiagnostic, Result
from panopticon.inventory.model import InstalledServer
from panopticon.registry.model import NormalizedHistory


@dataclass(frozen=True, slots=True)
class DoctorRequest:
    client: str | None = None
    list_clients: bool = False
    fix: bool = False
    offline: bool = False


@dataclass(frozen=True, slots=True)
class DoctorInstallation:
    installation_id: str
    name: str
    client: str
    transport: str
    command: str | None
    url: str | None
    config_path: str
    scope: str
    env_keys: tuple[str, ...] = ()
    headers_keys: tuple[str, ...] = ()
    history: NormalizedHistory | None = None


@dataclass(frozen=True, slots=True)
class DoctorServerGroup:
    server_id: str
    installations: tuple[DoctorInstallation, ...]


@dataclass(frozen=True, slots=True)
class DoctorClient:
    name: str
    status: str
    groups: tuple[DoctorServerGroup, ...] = ()


@dataclass(frozen=True, slots=True)
class DoctorData:
    clients: tuple[DoctorClient, ...] = ()
    alerts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DoctorOutcome:
    result: Result
    data: DoctorData = field(default_factory=DoctorData)


DoctorResult = DoctorOutcome


class RegistryLookup(Protocol):
    def __call__(self, server: InstalledServer) -> NormalizedHistory | None: ...


__all__ = [
    "ClientAdapter",
    "DiscoveryEnv",
    "DoctorClient",
    "DoctorData",
    "DoctorInstallation",
    "DoctorOutcome",
    "DoctorRequest",
    "DoctorResult",
    "DoctorServerGroup",
    "EngineDiagnostic",
    "RegistryLookup",
]
