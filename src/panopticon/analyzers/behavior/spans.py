"""Deterministic tracer-visible span construction and event attribution."""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from panopticon.models.ids import derive_span_id


class SpanKind(StrEnum):
    CALL = "call"
    SESSION = "session"
    INSTALL = "install"
    STARTUP = "startup"
    IDLE = "idle"
    SHUTDOWN = "shutdown"


class SpanPhase(StrEnum):
    START = "start"
    END = "end"


@dataclass(frozen=True, slots=True)
class SpanMarker:
    span_id: str
    kind: SpanKind
    phase: SpanPhase
    timestamp: float
    root_pid: int | None = None


@dataclass(frozen=True, slots=True)
class SpanBoundary:
    span_id: str
    start: datetime
    end: datetime
    kind: SpanKind = SpanKind.CALL
    root_pid: int | None = None


@dataclass(frozen=True, slots=True)
class SpanBuildResult:
    spans: tuple[SpanBoundary, ...]
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClockSample:
    tracer_timestamp: float
    collector_timestamp: float


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


def stable_span_id(tool: str, call_index: int) -> str:
    return derive_span_id(tool, call_index)


def calibrated_skew(samples: Iterable[ClockSample]) -> float | None:
    offsets = [sample.collector_timestamp - sample.tracer_timestamp for sample in samples]
    if len(offsets) < 2:
        return None
    return float(statistics.median(offsets))


def build_spans(markers: Iterable[SpanMarker]) -> SpanBuildResult:
    grouped: dict[str, list[SpanMarker]] = {}
    for marker in markers:
        grouped.setdefault(marker.span_id, []).append(marker)
    spans: list[SpanBoundary] = []
    diagnostics: list[str] = []
    for span_id in sorted(grouped):
        group = grouped[span_id]
        starts = [marker for marker in group if marker.phase is SpanPhase.START]
        ends = [marker for marker in group if marker.phase is SpanPhase.END]
        if len(starts) != 1 or len(ends) != 1:
            diagnostics.append(f"INCOMPLETE_SPAN:{span_id}")
            continue
        start, end = starts[0], ends[0]
        if start.kind is not end.kind or end.timestamp <= start.timestamp:
            diagnostics.append(f"INVALID_SPAN:{span_id}")
            continue
        spans.append(
            SpanBoundary(
                span_id,
                datetime.fromtimestamp(start.timestamp, tz=UTC),
                datetime.fromtimestamp(end.timestamp, tz=UTC),
                start.kind,
                start.root_pid,
            )
        )
    spans.sort(key=lambda span: (span.start, span.end, span.span_id))
    return SpanBuildResult(tuple(spans), tuple(diagnostics))


def attribute_span(
    timestamp: float,
    spans: Iterable[SpanBoundary],
    skew: float = 0.0,
) -> str | None:
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
        if span.start <= instant < span.end
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
