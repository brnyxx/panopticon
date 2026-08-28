"""Build strict persisted observations from completed local watch evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

from panopticon import __version__
from panopticon.analyzers.behavior.spans import AttributionContext, SpanBoundary, attribute_event
from panopticon.declared.model import DeclaredScope
from panopticon.models.common import PersistedPath
from panopticon.models.event import Event, FileEvent
from panopticon.models.ids import ObservationId, SpanId
from panopticon.models.observation import (
    DiscoveryReason,
    FallbackReason,
    LocalSandbox,
    Observation,
    ProtocolEra,
    ProtocolInfo,
    ServerInfo,
    Span,
    SpanResult,
    ToolAnnotations,
    ToolInfo,
)
from panopticon.probe.driver import CallStatus
from panopticon.sandbox.decoy_specs import FILE_SPECS
from panopticon.sandbox.trace_model import TraceEvent

from .watch_declared import build_declared
from .watch_events import convert_events, convert_network_events, persisted_path
from .watch_leaks import leak_events_by_span
from .watch_local_model import LocalSpan, LocalWatchResult
from .watch_state import build_state


@dataclass(frozen=True, slots=True)
class WatchObservationBuild:
    observation: Observation | None
    uncovered_events: int
    diagnostics: tuple[str, ...] = ()
    declared_scope: DeclaredScope | None = None
    reason_code: str = "OK"


def _observation_id(result: LocalWatchResult, observed_at: datetime) -> ObservationId:
    trace = tuple(
        (event.pid, event.timestamp, event.syscall, event.operation, event.path, event.peer)
        for event in (result.trace.events if result.trace is not None else ())
    )
    semantic = (
        str(result.context.target.installation_id),
        observed_at.isoformat(),
        result.status.value,
        result.reason_code,
        trace,
    )
    encoded = json.dumps(semantic, sort_keys=True, separators=(",", ":"))
    return ObservationId(f"obs_{hashlib.sha256(encoded.encode()).hexdigest()[:24]}")


def _decoy_paths(result: LocalWatchResult) -> dict[str, str]:
    manifest = result.manifest
    if manifest is None:
        return {}
    output: dict[str, str] = {}
    for spec in FILE_SPECS:
        marker = next(
            (item for item in manifest.markers if item.key.endswith(f":file:{spec.key}")),
            None,
        )
        if marker is not None and spec.path in manifest.files:
            output[f"~/{spec.path}"] = marker.key
    for path in manifest.files:
        marker = next(
            (item for item in manifest.markers if item.key.endswith(f":project:{path}")),
            None,
        )
        if marker is not None:
            output[f"~/{path}"] = marker.key
    return output


def _span_boundaries(spans: tuple[LocalSpan, ...]) -> tuple[SpanBoundary, ...]:
    tolerance = timedelta(milliseconds=50)
    return tuple(
        SpanBoundary(
            span.span_id,
            span.started_at - tolerance if span.kind.value == "call" else span.started_at,
            span.ended_at + tolerance if span.kind.value == "call" else span.ended_at,
            span.kind,
        )
        for span in spans
    )


def _assigned_events(
    result: LocalWatchResult,
) -> tuple[dict[str, list[TraceEvent]], int]:
    boundaries = _span_boundaries(result.spans)
    parents = tuple(
        (event.child_pid, event.pid)
        for event in (result.trace.events if result.trace is not None else ())
        if event.child_pid is not None
    )
    context = AttributionContext(boundaries, parents)
    call_context = AttributionContext(
        tuple(boundary for boundary in boundaries if boundary.kind.value == "call"),
        parents,
    )
    assigned: dict[str, list[TraceEvent]] = {span.span_id: [] for span in result.spans}
    uncovered = 0
    for event in result.trace.events if result.trace is not None else ():
        attribution = attribute_event(event.timestamp, event.pid, call_context)
        if attribution.span_id is None:
            attribution = attribute_event(event.timestamp, event.pid, context)
        if attribution.span_id is None:
            uncovered += 1
        else:
            assigned[attribution.span_id].append(event)
    return assigned, uncovered


def _span_result(result: LocalWatchResult, span: LocalSpan) -> SpanResult:
    if span.kind.value != "call" or result.calls is None:
        return SpanResult.OK
    call = next(
        (
            item
            for item in result.calls.calls
            if item.tool == span.tool and item.call_index == span.call_index
        ),
        None,
    )
    if call is None:
        return SpanResult.ERROR
    if call.status is CallStatus.SKIPPED:
        return SpanResult.SKIPPED
    if call.reason_code == "TIMEOUT":
        return SpanResult.TIMEOUT
    return SpanResult.OK if call.status is CallStatus.COMPLETE else SpanResult.ERROR


def build_watch_observation(
    result: LocalWatchResult,
    *,
    observed_at: datetime | None = None,
    tracer: str = "strace",
) -> WatchObservationBuild:
    protocol = result.protocol
    image = result.image
    runtime = result.runtime
    if (
        protocol is None
        or image is None
        or runtime not in {"docker", "podman"}
        or result.trace is None
        or result.manifest is None
        or not result.spans
    ):
        return WatchObservationBuild(None, 0, result.diagnostics, reason_code="EVIDENCE_INCOMPLETE")
    observed = observed_at or min(span.started_at for span in result.spans)
    if observed.tzinfo is None:
        return WatchObservationBuild(None, 0, result.diagnostics, reason_code="TIMEZONE_REQUIRED")
    observed = observed.astimezone(UTC)
    assigned, uncovered = _assigned_events(result)
    decoy_paths = _decoy_paths(result)
    leak_events = leak_events_by_span(result)
    snapshot_events = tuple(
        Event(
            FileEvent(
                schema_version="1.0",
                kind="file",
                op=operation,
                path=PersistedPath(persisted_path(path)),
                decoy=persisted_path(path) in decoy_paths,
                decoy_key=decoy_paths.get(persisted_path(path)),
                count=1,
            )
        )
        for operation, path in (result.snapshot.paths if result.snapshot else ())
    )
    network_events = convert_network_events(result.network_events)
    spans = tuple(
        Span(
            span_id=SpanId(span.span_id),
            tool=span.tool,
            call_index=span.call_index,
            args_fingerprint=span.args_fingerprint,
            result=_span_result(result, span),
            duration_ms=max(0, int((span.ended_at - span.started_at).total_seconds() * 1000)),
            events=(
                *convert_events(
                    assigned.get(span.span_id, ()),
                    decoy_paths=decoy_paths,
                    decoy_markers=result.manifest.markers if result.manifest else (),
                ),
                *(snapshot_events if span.kind.value == "session" else ()),
                *(network_events if span.kind.value == "session" else ()),
                *leak_events.get(span.span_id, ()),
            ),
        )
        for span in result.spans
    )
    declaration = build_declared(result)
    state = build_state(result, declaration.persisted.completeness, uncovered_events=uncovered)
    image_name, image_digest = image.rsplit("@", 1)
    runtime_name = cast(Literal["docker", "podman"], runtime)
    package = result.context.target.package
    observation = Observation(
        schema_version="1.0",
        observation_id=_observation_id(result, observed),
        server_id=result.context.target.server_id,
        installation_id=result.context.target.installation_id,
        observed_at=observed,
        pano_version=__version__,
        sandbox=LocalSandbox(
            runtime=runtime_name,
            image=image_name,
            image_digest=image_digest,
            tracer=tracer,
        ),
        package_resolved=(package.resolved or package.pinned) if package is not None else None,
        protocol=ProtocolInfo(
            era=ProtocolEra(protocol.era.value),
            requested_version=protocol.requested_version,
            selected_version=protocol.selected_version,
            discovery_reason=(
                DiscoveryReason.MODERN_METADATA
                if protocol.era.value == "modern"
                else DiscoveryReason.LEGACY_HANDSHAKE
            ),
            fallback_reason=(
                FallbackReason.LEGACY_REQUIRED if protocol.fallback else FallbackReason.NONE
            ),
            server_info=ServerInfo(name=protocol.server_name, version=protocol.server_version),
            capabilities=protocol.capabilities,
        ),
        tools=tuple(
            ToolInfo(
                name=tool.name,
                input_schema_hash=tool.input_schema_hash,
                annotations=ToolAnnotations(
                    read_only=tool.read_only,
                    destructive=tool.destructive,
                    open_world=tool.open_world,
                ),
            )
            for tool in result.tools
        ),
        spans=spans,
        declared=declaration.persisted,
        findings=(),
        state=state,
    )
    diagnostics = (*result.diagnostics, *(("UNATTRIBUTED_EVENTS",) if uncovered else ()))
    return WatchObservationBuild(
        observation,
        uncovered,
        diagnostics,
        declaration.scope,
    )


__all__ = ["WatchObservationBuild", "build_watch_observation"]
