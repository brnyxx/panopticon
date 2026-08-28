"""Deterministic grouping and leak-safe projection of inventory records."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from panopticon.engine.doctor_model import DoctorInstallation, DoctorServerGroup
from panopticon.inventory.model import InstalledServer
from panopticon.registry.model import NormalizedHistory


def project_installation(
    server: InstalledServer,
    history: NormalizedHistory | None = None,
) -> DoctorInstallation:
    # Values are already normalized; secrets are represented only by key names.
    return DoctorInstallation(
        installation_id=str(server.installation_id),
        name=str(server.name),
        client=str(server.client),
        transport=server.transport.value,
        command=server.command,
        url=str(server.url) if server.url else None,
        config_path=str(server.config_path),
        scope=server.scope.value,
        env_keys=tuple(str(x) for x in server.env_keys),
        headers_keys=tuple(str(x) for x in server.headers_keys),
        history=history,
    )


def group_installations(
    servers: Iterable[InstalledServer],
    histories: Mapping[str, NormalizedHistory] | None = None,
) -> tuple[DoctorServerGroup, ...]:
    grouped: dict[str, list[InstalledServer]] = {}
    for server in servers:
        grouped.setdefault(str(server.server_id), []).append(server)
    out: list[DoctorServerGroup] = []
    for sid in sorted(grouped):
        items = sorted(grouped[sid], key=lambda value: str(value.installation_id))
        projected = tuple(
            project_installation(item, (histories or {}).get(str(item.installation_id)))
            for item in items
        )
        out.append(DoctorServerGroup(server_id=sid, installations=projected))
    return tuple(out)


__all__ = ["group_installations", "project_installation"]
