"""Normalize observation evidence into deterministic, span-attributed records."""

from __future__ import annotations

import ipaddress
import posixpath
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from panopticon.sandbox.trace import TraceEvent


class EvidenceSource(StrEnum):
    TRACE = "trace"
    SNAPSHOT = "snapshot"
    PROXY = "proxy"
    DNS = "dns"


class CoverageState(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NOT_REQUESTED = "NOT_REQUESTED"


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
    child_pid: int | None = None
    certainty: bool = True


@dataclass(frozen=True, slots=True)
class SourceCoverage:
    status: CoverageState
    reason_code: str


_NOT_REQUESTED = SourceCoverage(CoverageState.NOT_REQUESTED, "NOT_REQUESTED")


@dataclass(frozen=True, slots=True)
class Coverage:
    trace: SourceCoverage = _NOT_REQUESTED
    snapshot: SourceCoverage = _NOT_REQUESTED
    proxy: SourceCoverage = _NOT_REQUESTED
    dns: SourceCoverage = _NOT_REQUESTED

    @property
    def partial(self) -> bool:
        return any(
            source.status is CoverageState.PARTIAL
            for source in (self.trace, self.snapshot, self.proxy, self.dns)
        )


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
                    event.child_pid,
                    event.confirmed,
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
                    event.child_pid,
                    event.confirmed,
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
                    event.child_pid,
                    event.confirmed,
                )
            )
    return out


def collect_behavior(
    trace: Iterable[TraceEvent] | None = None,
    snapshot: Iterable[str] | None = None,
    proxy: Iterable[str] | None = None,
    dns: Iterable[str] | None = None,
    *,
    truncated_sources: frozenset[EvidenceSource] = frozenset(),
) -> CollectionResult:
    """Merge heterogeneous evidence by stable semantic keys; never infer absent data."""
    trace_items = tuple(trace or ())
    snapshot_items = tuple(snapshot or ())
    proxy_items = tuple(proxy or ())
    dns_items = tuple(dns or ())
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
    unique: dict[
        tuple[str, str, str, str, int | None, float | None, int | None, bool],
        Evidence,
    ] = {}
    for item in items:
        key = (
            item.kind,
            item.value,
            item.operation,
            item.source.value,
            item.pid,
            item.timestamp,
            item.child_pid,
            item.certainty,
        )
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
                x.child_pid or 0,
                x.certainty,
            ),
        )
    )
    return CollectionResult(
        ordered,
        Coverage(
            _coverage(EvidenceSource.TRACE, trace is not None, truncated_sources),
            _coverage(EvidenceSource.SNAPSHOT, snapshot is not None, truncated_sources),
            _coverage(EvidenceSource.PROXY, proxy is not None, truncated_sources),
            _coverage(EvidenceSource.DNS, dns is not None, truncated_sources),
        ),
        tuple(
            f"{source.value.upper()}_OVERFLOW"
            for source in sorted(
                truncated_sources,
                key=lambda item: item.value,
            )
        ),
    )


def _coverage(
    source: EvidenceSource,
    requested: bool,
    truncated_sources: frozenset[EvidenceSource],
) -> SourceCoverage:
    if not requested:
        return _NOT_REQUESTED
    if source in truncated_sources:
        return SourceCoverage(CoverageState.PARTIAL, "BUFFER_OVERFLOW")
    return SourceCoverage(CoverageState.COMPLETE, "COMPLETED")


collect = collect_behavior
