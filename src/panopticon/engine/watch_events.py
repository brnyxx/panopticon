"""Convert parsed tracer records into deduplicated persisted events."""

from __future__ import annotations

import ast
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Literal

from panopticon.models.common import Host, PersistedPath
from panopticon.models.event import Event, FileEvent, NetEvent, PlaintextHttpEvent, ProcessEvent
from panopticon.sandbox.decoy import DecoyMarker
from panopticon.sandbox.matcher import DecoyMatcher
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


def _argv(event: TraceEvent, decoy_markers: tuple[DecoyMarker, ...] = ()) -> tuple[str, ...]:
    if len(event.arguments) > 1:
        try:
            value: object = ast.literal_eval(event.arguments[1])
        except (SyntaxError, ValueError):
            value = None
        if isinstance(value, list):
            strings = tuple(item for item in value if isinstance(item, str) and item)
            if strings and len(strings) == len(value):
                replacements = {marker.text: f"<{marker.key}>" for marker in decoy_markers}
                return tuple(replacements.get(item, item) for item in strings)
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
    decoy_markers: Iterable[DecoyMarker] = (),
    proxy_hosts: frozenset[str] = frozenset(),
) -> tuple[Event, ...]:
    path_keys = decoy_paths or {}
    files: Counter[tuple[FileOperation, str, bool, str | None]] = Counter()
    processes: Counter[tuple[str, ...]] = Counter()
    networks: Counter[tuple[str, int | None, NetworkVia]] = Counter()
    plaintext: Counter[tuple[str, str, tuple[str, ...]]] = Counter()
    marker_set = tuple(decoy_markers)
    for event in events:
        operation = _file_operation(event)
        if operation is not None and event.path:
            path = persisted_path(event.path)
            decoy_key = path_keys.get(path)
            files[(operation, path, decoy_key is not None, decoy_key)] += 1
        elif event.operation == "exec" and event.path:
            processes[_argv(event, marker_set)] += 1
        elif event.operation == "connect" and event.peer:
            host, port = _peer(event.peer)
            if host is not None:
                networks[(host.casefold(), port, "proxy" if host in proxy_hosts else "direct")] += 1
        elif event.operation == "send" and event.arguments:
            payload = ""
            if len(event.arguments) > 1:
                try:
                    value = ast.literal_eval(event.arguments[1])
                    if isinstance(value, bytes):
                        payload = value.decode("utf-8", errors="replace")
                    elif isinstance(value, str):
                        payload = value
                except (SyntaxError, ValueError):
                    pass
            if payload.startswith(("GET ", "POST ", "PUT ", "PATCH ", "DELETE ")):
                request_line, _, headers = payload.partition("\r\n")
                path = request_line.split(" ", 2)[1] if len(request_line.split(" ", 2)) > 1 else "/"
                host_match = re.search(r"(?im)^Host:\s*([^\r\n]+)", headers)
                host = host_match.group(1).strip() if host_match else "unknown"
                report = DecoyMatcher(marker_set).match((payload.encode(),))
                keys = tuple(sorted({match.key for match in report.matches}))
                if keys:
                    plaintext[(host, path, keys)] += 1
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
    for (host, path, keys), count in sorted(plaintext.items()):
        output.append(
            Event(
                PlaintextHttpEvent(
                    schema_version="1.0",
                    kind="plaintext_http",
                    op="request",
                    host=Host(host),
                    request_path=path if path.startswith("/") else "/",
                    decoy_keys=keys,
                    count=count,
                )
            )
        )
    return tuple(output)


__all__ = ["convert_events", "persisted_path"]
