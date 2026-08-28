"""Normalize observation evidence into deterministic, span-attributed records."""

from __future__ import annotations

import ipaddress
import posixpath
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from panopticon.sandbox.trace import TraceEvent


class EvidenceSource(StrEnum):
    TRACE = "trace"
    SNAPSHOT = "snapshot"
    PROXY = "proxy"
    DNS = "dns"


class AccessSemantics(StrEnum):
    READ = "read"
    WRITE = "write"
    METADATA = "metadata"
    EXECUTE = "execute"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Evidence:
    kind: str
    value: str
    operation: str
    source: EvidenceSource
    pid: int | None = None
    timestamp: float | None = None
    certainty: bool = True


@dataclass(frozen=True, slots=True)
class Coverage:
    trace: bool = False
    snapshot: bool = False
    proxy: bool = False
    dns: bool = False
    partial: bool = False


@dataclass(frozen=True, slots=True)
class SpanBoundary:
    span_id: str
    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class CollectionResult:
    evidence: tuple[Evidence, ...]
    coverage: Coverage
    diagnostics: tuple[str, ...] = ()


def normalize_path(path: str, home: str = "/home/pano") -> str:
    """Convert container paths to stable ``~`` relative paths."""
    if path == "~" or path.startswith("~/"):
        return posixpath.normpath(path)
    path = re.sub(r"/{2,}", "/", path)
    if path == home or path.startswith(home.rstrip("/") + "/"):
        suffix = path[len(home) :].lstrip("/")
        return "~" + ("/" + suffix if suffix else "")
    normalized = posixpath.normpath(path)
    return normalized if normalized.startswith("/") else "/" + normalized


def normalize_host(value: str) -> str:
    value = value.strip().strip('"')
    for pattern in (
        r"(?:inet_addr|sin_addr)=?\"([^\"]+)\"",
        r"sin6_addr=inet_pton\(AF_INET6,\s*\"([^\"]+)\"\)",
        r"sun_path=([^,}]+)",
    ):
        match = re.search(pattern, value)
        if match:
            value = match.group(1).strip('"')
            break
    if value.startswith("[") and "]" in value:
        return value[1 : value.index("]")].lower()
    if value.startswith("unix:"):
        return value.lower()
    host, sep, port = value.rpartition(":")
    if sep and port.isdigit() and host:
        value = host
    try:
        return ipaddress.ip_address(value).compressed.lower()
    except ValueError:
        return value.rstrip(".").lower()


def classify_access(event: TraceEvent) -> AccessSemantics:
    if event.operation in {"exec"}:
        return AccessSemantics.EXECUTE
    if event.operation in {"stat"}:
        return AccessSemantics.METADATA
    if event.operation in {"read"}:
        return AccessSemantics.READ
    if event.operation in {"send", "bind", "connect"}:
        return AccessSemantics.WRITE
    return AccessSemantics.UNKNOWN


def _trace_items(events: Iterable[TraceEvent]) -> list[Evidence]:
    out: list[Evidence] = []
    for event in events:
        if event.path is not None:
            out.append(
                Evidence(
                    "file",
                    normalize_path(event.path),
                    classify_access(event).value,
                    EvidenceSource.TRACE,
                    event.pid,
                    event.timestamp,
                )
            )
        elif event.peer is not None:
            out.append(
                Evidence(
                    "network",
                    normalize_host(event.peer),
                    event.operation,
                    EvidenceSource.TRACE,
                    event.pid,
                    event.timestamp,
                )
            )
        elif event.operation in {"clone", "fork"}:
            out.append(
                Evidence(
                    "process",
                    event.syscall,
                    event.operation,
                    EvidenceSource.TRACE,
                    event.pid,
                    event.timestamp,
                )
            )
    return out


def collect_behavior(
    trace: Iterable[TraceEvent] = (),
    snapshot: Iterable[str] = (),
    proxy: Iterable[str] = (),
    dns: Iterable[str] = (),
    *,
    truncated: bool = False,
) -> CollectionResult:
    """Merge heterogeneous evidence by stable semantic keys; never infer absent data."""
    trace_items = tuple(trace)
    snapshot_items = tuple(snapshot)
    proxy_items = tuple(proxy)
    dns_items = tuple(dns)
    items = _trace_items(trace_items)
    items.extend(
        Evidence(
            "file",
            normalize_path(p),
            AccessSemantics.UNKNOWN.value,
            EvidenceSource.SNAPSHOT,
            certainty=False,
        )
        for p in snapshot_items
    )
    items.extend(
        Evidence("network", normalize_host(h), "connect", EvidenceSource.PROXY) for h in proxy_items
    )
    items.extend(
        Evidence("network", normalize_host(h), "dns", EvidenceSource.DNS) for h in dns_items
    )
    unique: dict[tuple[str, str, str, str, int | None, float | None], Evidence] = {}
    for item in items:
        key = (item.kind, item.value, item.operation, item.source.value, item.pid, item.timestamp)
        unique[key] = item
    ordered = tuple(
        sorted(
            unique.values(),
            key=lambda x: (
                x.kind,
                x.value,
                x.operation,
                x.source.value,
                x.pid or 0,
                x.timestamp or 0.0,
            ),
        )
    )
    return CollectionResult(
        ordered,
        Coverage(
            bool(trace_items), bool(snapshot_items), bool(proxy_items), bool(dns_items), truncated
        ),
        ("TRUNCATED",) if truncated else (),
    )


def attribute_span(
    timestamp: float, spans: Iterable[SpanBoundary], skew: float = 0.0
) -> str | None:
    """Assign only events inside a span after injected clock correction."""
    instant = datetime.fromtimestamp(timestamp + skew, tz=UTC)
    matches = [span for span in spans if span.start <= instant <= span.end]
    if not matches:
        return None
    return min(matches, key=lambda span: (span.end - span.start, span.span_id)).span_id


collect = collect_behavior
