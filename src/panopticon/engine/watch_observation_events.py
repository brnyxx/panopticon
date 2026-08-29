"""Event attribution and conversion for persisted watch observations."""

from __future__ import annotations

from datetime import timedelta

from panopticon.analyzers.behavior.spans import AttributionContext, SpanBoundary, attribute_event
from panopticon.models.common import PersistedPath
from panopticon.models.event import Event, FileEvent
from panopticon.models.ids import SpanId
from panopticon.models.observation import Span, SpanResult
from panopticon.probe.driver import CallStatus
from panopticon.sandbox.decoy_specs import FILE_SPECS
from panopticon.sandbox.netlog import NetworkEvent
from panopticon.sandbox.trace_model import TraceEvent

from .watch_events import convert_events, convert_network_events, persisted_path
from .watch_leaks import leak_events_by_span
from .watch_local_model import LocalSpan, LocalWatchResult


def decoy_paths(result: LocalWatchResult) -> dict[str, str]:
    if result.manifest is None:
        return {}
    output: dict[str, str] = {}
    for spec in FILE_SPECS:
        marker = next(
            (item for item in result.manifest.markers if item.key.endswith(f":file:{spec.key}")),
            None,
        )
        if marker is not None and spec.path in result.manifest.files:
            output[f"~/{spec.path}"] = marker.key
    for path in result.manifest.files:
        marker = next(
            (item for item in result.manifest.markers if item.key.endswith(f":project:{path}")),
            None,
        )
        if marker is not None:
            output[f"~/{path}"] = marker.key
    return output


def assigned_events(
    result: LocalWatchResult,
    events: tuple[TraceEvent, ...] | None = None,
) -> tuple[dict[str, list[TraceEvent]], int]:
    tolerance = timedelta(milliseconds=50)
    boundaries = tuple(
        SpanBoundary(
            span.span_id,
            span.started_at,
            span.ended_at,
            span.kind,
        )
        for span in result.spans
    )
    parents = tuple(
        (event.child_pid, event.pid)
        for event in (result.trace.events if result.trace is not None else ())
        if event.child_pid is not None
    )
    context = AttributionContext(
        tuple(
            boundary for boundary in boundaries if boundary.kind.value not in {"session", "startup"}
        ),
        parents,
    )
    call_context = AttributionContext(
        tuple(
            SpanBoundary(
                boundary.span_id,
                boundary.start - tolerance,
                boundary.end + tolerance,
                boundary.kind,
            )
            for boundary in boundaries
            if boundary.kind.value == "call"
        ),
        parents,
    )
    fallback_context = AttributionContext(
        tuple(boundary for boundary in boundaries if boundary.kind.value in {"session", "startup"}),
        parents,
    )
    assigned: dict[str, list[TraceEvent]] = {span.span_id: [] for span in result.spans}
    uncovered = 0
    source_events = (
        events if events is not None else (result.trace.events if result.trace is not None else ())
    )
    for event in source_events:
        attribution = attribute_event(event.timestamp, event.pid, context)
        if attribution.span_id is None:
            attribution = attribute_event(event.timestamp, event.pid, call_context)
        if attribution.span_id is None:
            attribution = attribute_event(event.timestamp, event.pid, fallback_context)
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


def build_observation_events(
    result: LocalWatchResult,
    assigned: dict[str, list[TraceEvent]],
    decoys: dict[str, str],
) -> tuple[Span, ...]:
    snapshot_events = tuple(
        Event(
            FileEvent(
                schema_version="1.0",
                kind="file",
                op=operation,
                path=PersistedPath(persisted_path(path)),
                decoy=persisted_path(path) in decoys,
                decoy_key=decoys.get(persisted_path(path)),
                count=1,
            )
        )
        for operation, path in (result.snapshot.paths if result.snapshot else ())
    )
    network_by_span: dict[str, list[NetworkEvent]] = {span.span_id: [] for span in result.spans}
    session_spans = [span for span in result.spans if span.kind.value == "session"]
    call_spans = [span for span in result.spans if span.kind.value == "call"]
    other_spans = [span for span in result.spans if span.kind.value not in {"session", "call"}]
    for network_event in result.network_events:
        target = None
        timestamp = getattr(network_event, "timestamp", None)
        if timestamp is not None:
            target = next(
                (span for span in call_spans if span.started_at <= timestamp <= span.ended_at),
                None,
            )
            if target is None:
                target = next(
                    (span for span in other_spans if span.started_at <= timestamp <= span.ended_at),
                    None,
                )
            if target is None:
                target = next(
                    (
                        span
                        for span in session_spans
                        if span.started_at <= timestamp <= span.ended_at
                    ),
                    None,
                )
        if target is None and timestamp is None and session_spans:
            target = session_spans[0]
        if target is not None:
            network_by_span[target.span_id].append(network_event)
    leaks = leak_events_by_span(result)
    return tuple(
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
                    decoy_paths=decoys,
                    decoy_markers=result.manifest.markers if result.manifest else (),
                ),
                *(snapshot_events if span.kind.value == "session" else ()),
                *convert_network_events(network_by_span.get(span.span_id, ())),
                *leaks.get(span.span_id, ()),
            ),
        )
        for span in result.spans
    )


__all__ = ["assigned_events", "build_observation_events", "decoy_paths"]
