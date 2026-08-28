"""Convert parsed tracer records into deduplicated persisted events."""

from __future__ import annotations

import ast
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Literal

from panopticon.models.common import Host, PersistedPath
from panopticon.models.event import Event, FileEvent, NetEvent, ProcessEvent
from panopticon.sandbox.trace_model import TraceEvent


def persisted_path(path: str) -> str:
    normalized = path.translate(str.maketrans("\\", "/"))
    for prefix in ("/home/pano", "/root"):
        if normalized == prefix:
            return "~"
        if normalized.startswith(f"{prefix}/"):
            return f"~{normalized[len(prefix) :]}"
    return normalized


FileOperation = Literal["read", "write", "stat", "create"]
NetworkVia = Literal["proxy", "direct"]


def _file_operation(event: TraceEvent) -> FileOperation | None:
    if event.operation == "read":
        return "read"
    if event.operation == "write":
        return "write"
    if event.operation == "stat":
        return "stat"
    if event.operation != "open":
        return None
    flags = event.arguments[-1] if event.arguments else ""
    if "O_CREAT" in flags:
        return "create"
    if any(flag in flags for flag in ("O_WRONLY", "O_RDWR", "O_TRUNC", "O_APPEND")):
        return "write"
    return "read"


def _argv(event: TraceEvent) -> tuple[str, ...]:
    if len(event.arguments) > 1:
        try:
            value: object = ast.literal_eval(event.arguments[1])
        except (SyntaxError, ValueError):
            value = None
        if (
            isinstance(value, list)
            and value
            and all(isinstance(item, str) and item for item in value)
        ):
            return tuple(value)
    return (event.path or "unknown",)


def _peer(value: str) -> tuple[str | None, int | None]:
    host_match = re.search(
        r'(?:inet_addr\(\s*"([^"]+)"|inet_pton\([^,]+,\s*"([^"]+)")',
        value,
    )
    host = next((group for group in host_match.groups() if group), None) if host_match else None
    port_match = re.search(r"(?:sin6?_port=)?htons\((\d+)\)", value)
    return host, int(port_match.group(1)) if port_match else None


def convert_events(
    events: Iterable[TraceEvent],
    *,
    decoy_paths: Mapping[str, str] | None = None,
    proxy_hosts: frozenset[str] = frozenset(),
) -> tuple[Event, ...]:
    path_keys = decoy_paths or {}
    files: Counter[tuple[FileOperation, str, bool, str | None]] = Counter()
    processes: Counter[tuple[str, ...]] = Counter()
    networks: Counter[tuple[str, int | None, NetworkVia]] = Counter()
    for event in events:
        operation = _file_operation(event)
        if operation is not None and event.path:
            path = persisted_path(event.path)
            decoy_key = path_keys.get(path)
            files[(operation, path, decoy_key is not None, decoy_key)] += 1
        elif event.operation == "exec" and event.path:
            processes[_argv(event)] += 1
        elif event.operation == "connect" and event.peer:
            host, port = _peer(event.peer)
            if host is not None:
                networks[(host.casefold(), port, "proxy" if host in proxy_hosts else "direct")] += 1
    output: list[Event] = []
    for (operation, path, decoy, key), count in sorted(files.items()):
        output.append(
            Event(
                FileEvent(
                    schema_version="1.0",
                    kind="file",
                    op=operation,
                    path=PersistedPath(path),
                    decoy=decoy,
                    decoy_key=key,
                    count=count,
                )
            )
        )
    for argv, count in sorted(processes.items()):
        output.append(
            Event(
                ProcessEvent(
                    schema_version="1.0",
                    kind="proc",
                    op="exec",
                    argv=argv,
                    count=count,
                )
            )
        )
    for (host, port, via), count in sorted(networks.items()):
        output.append(
            Event(
                NetEvent(
                    schema_version="1.0",
                    kind="net",
                    op="connect",
                    host=Host(host),
                    port=port,
                    via=via,
                    count=count,
                )
            )
        )
    return tuple(output)


__all__ = ["convert_events", "persisted_path"]
