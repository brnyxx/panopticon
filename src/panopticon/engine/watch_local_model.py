"""Typed, non-persisted evidence from one local watch session."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from panopticon.analyzers.behavior.spans import SpanKind
from panopticon.probe.argument_schema import JsonValue
from panopticon.probe.driver import DriverResult
from panopticon.probe.protocol import ProtocolEra
from panopticon.sandbox.base import StreamResult
from panopticon.sandbox.decoy import DecoyManifest
from panopticon.sandbox.netlog import NetworkEvent
from panopticon.sandbox.snapshot import SnapshotDiff
from panopticon.sandbox.trace_model import TraceResult

from .watch_inventory import WatchTargetContext
from .watch_model import Coverage


class LocalWatchStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INCOMPLETE = "INCOMPLETE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class LocalProtocol:
    era: ProtocolEra
    requested_version: str
    selected_version: str
    fallback: bool
    server_name: str
    server_version: str
    capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LocalTool:
    name: str
    input_schema_hash: str
    read_only: bool
    destructive: bool
    open_world: bool


@dataclass(frozen=True, slots=True)
class LocalSpan:
    span_id: str
    tool: str
    call_index: int
    started_at: datetime
    ended_at: datetime
    args_fingerprint: str
    result: str
    kind: SpanKind = SpanKind.CALL


@dataclass(frozen=True, slots=True)
class LocalWatchResult:
    context: WatchTargetContext
    status: LocalWatchStatus
    reason_code: str
    image: str | None = None
    runtime: str | None = None
    offline: bool = False
    protocol: LocalProtocol | None = None
    tools: tuple[LocalTool, ...] = ()
    raw_tools: tuple[dict[str, JsonValue], ...] = field(default=(), repr=False)
    calls: DriverResult | None = None
    spans: tuple[LocalSpan, ...] = ()
    trace: TraceResult | None = field(default=None, repr=False)
    stderr: StreamResult | None = field(default=None, repr=False)
    notifications: tuple[dict[str, JsonValue], ...] = field(default=(), repr=False)
    manifest: DecoyManifest | None = field(default=None, repr=False)
    coverage: Mapping[str, Coverage] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()
    snapshot: SnapshotDiff | None = field(default=None, repr=False)
    network_events: tuple[NetworkEvent, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "coverage", MappingProxyType(dict(self.coverage)))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


__all__ = [
    "LocalProtocol",
    "LocalSpan",
    "LocalTool",
    "LocalWatchResult",
    "LocalWatchStatus",
]
