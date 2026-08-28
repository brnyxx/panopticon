"""Conversion of discovered raw entries into immutable InstalledServer records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import AnyHttpUrl

from panopticon.discovery.base import RawServerEntry
from panopticon.inventory.parsers import normalize_url, parse_command, resolve_cached_version
from panopticon.models.ids import (
    ClientName,
    InstallationIdentityComponents,
    ServerId,
    derive_installation_id,
)
from panopticon.models.inventory import (
    IdentityConfidence,
    InstallationSource,
    InstalledServer,
    Transport,
)


@dataclass(frozen=True, slots=True)
class InventoryGroup:
    server_id: ServerId
    installations: tuple[InstalledServer, ...]


def normalize_entry(
    entry: RawServerEntry, *, client: ClientName | str, home: str
) -> InstalledServer:
    client = client if isinstance(client, ClientName) else ClientName(client)
    raw: Mapping[str, object] = entry.raw
    command = raw.get("command")
    args_raw = raw.get("args", [])
    args = tuple(str(x) for x in args_raw) if isinstance(args_raw, list) else ()
    url_value = raw.get("url")
    transport_name = raw.get("transport")
    transport = (
        Transport.SSE
        if isinstance(transport_name, str) and transport_name.casefold() == "sse"
        else Transport.HTTP
        if isinstance(url_value, str)
        else Transport.STDIO
    )
    parsed = (
        parse_command(str(command), args) if isinstance(command, str) else parse_command("", args)
    )
    config_path = entry.logical_path
    installation_id = derive_installation_id(
        InstallationIdentityComponents(
            client=client,
            config_path=config_path,
            scope=entry.scope,
            config_pointer=entry.json_pointer,
            entry_name=entry.name,
        )
    )
    normalized_url = normalize_url(url_value) if isinstance(url_value, str) else None
    url = AnyHttpUrl(normalized_url) if normalized_url is not None else None
    if normalized_url is not None and not isinstance(command, str):
        parsed = parse_command("", (normalized_url,))
    env = raw.get("env", {})
    headers = raw.get("headers", {})
    return InstalledServer(
        schema_version="1.0",
        server_id=ServerId(parsed.server_id),
        installation_id=installation_id,
        name=entry.name,
        client=client,
        config_path=config_path,
        config_pointer=entry.json_pointer,
        scope=entry.scope,
        transport=transport,
        command=str(command) if isinstance(command, str) else None,
        args=args,
        env_keys=tuple(sorted(str(k) for k in env)) if isinstance(env, Mapping) else (),
        url=url,
        headers_keys=tuple(sorted(str(k) for k in headers)) if isinstance(headers, Mapping) else (),
        package=(
            parsed.package.model_copy(
                update={"resolved": resolve_cached_version(parsed.package, Path(home))}
            )
            if parsed.package is not None
            else None
        ),
        source=InstallationSource(kind=parsed.source, url=url),
        identity_confidence=IdentityConfidence(parsed.confidence),
        disabled=raw.get("disabled") is True or raw.get("enabled") is False,
        wrapped=raw.get("wrapped") is True,
    )


def normalize_entries(
    entries: list[RawServerEntry], *, client: ClientName | str, home: str
) -> tuple[InstalledServer, ...]:
    return tuple(
        sorted(
            (normalize_entry(e, client=client, home=home) for e in entries),
            key=lambda x: str(x.installation_id),
        )
    )


def group_servers(servers: tuple[InstalledServer, ...]) -> tuple[InventoryGroup, ...]:
    """Group for rendering without merging installation records."""
    grouped: dict[ServerId, list[InstalledServer]] = {}
    for server in servers:
        grouped.setdefault(server.server_id, []).append(server)
    return tuple(
        InventoryGroup(
            server_id=server_id,
            installations=tuple(
                sorted(grouped[server_id], key=lambda item: str(item.installation_id))
            ),
        )
        for server_id in sorted(grouped, key=str)
    )
