from __future__ import annotations

from panopticon.analyzers.behavior.collectors import (
    CoverageState,
    EvidenceSource,
    collect_behavior,
)
from panopticon.analyzers.behavior.spans import (
    AttributionContext,
    SpanKind,
    SpanMarker,
    SpanPhase,
    attribute_event,
    build_spans,
    stable_span_id,
)


def test_two_calls_have_exact_non_overlapping_span_ids() -> None:
    first = stable_span_id("search", 0)
    second = stable_span_id("search", 1)
    built = build_spans(
        (
            SpanMarker(first, SpanKind.CALL, SpanPhase.START, 1_700_000_000.0, 10),
            SpanMarker(first, SpanKind.CALL, SpanPhase.END, 1_700_000_001.0, 10),
            SpanMarker(second, SpanKind.CALL, SpanPhase.START, 1_700_000_001.0, 10),
            SpanMarker(second, SpanKind.CALL, SpanPhase.END, 1_700_000_002.0, 10),
        )
    )
    context = AttributionContext(built.spans, ((11, 10),))

    inside_first = attribute_event(1_700_000_000.5, 11, context)
    boundary = attribute_event(1_700_000_001.0, 11, context)

    assert built.diagnostics == ()
    assert inside_first.span_id == first
    assert boundary.span_id == second
    assert not inside_first.ambiguous
    assert not boundary.ambiguous


def test_buffer_overflow_preserves_partial_observation() -> None:
    result = collect_behavior(
        trace=(),
        proxy=("example.test:443",),
        truncated_sources=frozenset({EvidenceSource.PROXY}),
    )

    assert result.evidence[0].value == "example.test"
    assert result.coverage.trace.status is CoverageState.COMPLETE
    assert result.coverage.proxy.status is CoverageState.PARTIAL
    assert result.coverage.proxy.reason_code == "BUFFER_OVERFLOW"
    assert result.coverage.dns.status is CoverageState.NOT_REQUESTED
    assert result.diagnostics == ("PROXY_OVERFLOW",)
