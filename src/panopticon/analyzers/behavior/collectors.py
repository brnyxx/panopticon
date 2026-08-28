"""Normalize observation evidence into deterministic, span-attributed records."""

from __future__ import annotations

import ipaddress
import posixpath
import re
from collections.abc import Iterable, Mapping
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


class SpanKind(StrEnum):
    CALL = "call"
    STARTUP = "startup"
    IDLE = "idle"
    POST_CALL = "post_call"


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
    kind: SpanKind = SpanKind.CALL
    root_pid: int | None = None


@dataclass(frozen=True, slots=True)
class AttributionContext:
    spans: tuple[SpanBoundary, ...]
    process_parents: tuple[tuple[int, int], ...]
    skew: float = 0.0


@dataclass(frozen=True, slots=True)
class SpanAttribution:
    span_id: str | None
    ambiguous: bool
    reason_code: str


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
    normalized = posixpath.normpath(path)
    if normalized == home or normalized.startswith(home.rstrip("/") + "/"):
        suffix = normalized[len(home) :].lstrip("/")
        return "~" + ("/" + suffix if suffix else "")
    return normalized if normalized.startswith("/") else "/" + normalized


def normalize_host(value: str) -> str:
    value = value.strip().strip('"')
    for pattern in (
        r"sin_addr=inet_addr\(\"([^\"]+)\"\)",
        r"(?:inet_addr|sin_addr)=?\"([^\"]+)\"",
        r"sin6_addr=inet_pton\(AF_INET6,\s*\"([^\"]+)\"\)",
    ):
        match = re.search(pattern, value)
        if match:
            value = match.group(1).strip('"')
            break
    unix_match = re.search(r"sun_path=\"?([^\",}]+)", value)
    if unix_match:
        return f"unix:{unix_match.group(1)}"
    if value.startswith("[") and "]" in value:
        return value[1 : value.index("]")].lower()
    if value.startswith("unix:"):
        return value.lower()
    try:
        return ipaddress.ip_address(value).compressed.lower()
    except ValueError:
        pass
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
    if event.operation in {"write", "send", "bind", "connect"}:
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
    context = AttributionContext(tuple(spans), (), skew)
    return attribute_event(timestamp, None, context).span_id


def attribute_event(
    timestamp: float,
    pid: int | None,
    context: AttributionContext,
) -> SpanAttribution:
    """Attribute by corrected time and process ancestry without guessing ties."""
    instant = datetime.fromtimestamp(timestamp + context.skew, tz=UTC)
    parents = dict(context.process_parents)
    matches = [
        span
        for span in context.spans
        if span.start <= instant <= span.end
        and (
            span.root_pid is None
            or (pid is not None and _descends_from(pid, span.root_pid, parents))
        )
    ]
    if not matches:
        return SpanAttribution(None, False, "NO_MATCHING_SPAN")
    shortest = min(span.end - span.start for span in matches)
    candidates = [span for span in matches if span.end - span.start == shortest]
    if len(candidates) != 1:
        return SpanAttribution(None, True, "AMBIGUOUS_SPAN")
    return SpanAttribution(candidates[0].span_id, False, "ATTRIBUTED")


def _descends_from(pid: int, root_pid: int, parents: Mapping[int, int]) -> bool:
    current = pid
    visited: set[int] = set()
    while current not in visited:
        if current == root_pid:
            return True
        visited.add(current)
        parent = parents.get(current)
        if parent is None:
            return False
        current = parent
    return False


collect = collect_behavior
