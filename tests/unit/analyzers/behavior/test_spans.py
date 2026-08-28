from __future__ import annotations

from datetime import UTC, datetime

from panopticon.analyzers.behavior.spans import (
    AttributionContext,
    ClockSample,
    SpanKind,
    SpanMarker,
    SpanPhase,
    attribute_event,
    build_spans,
    calibrated_skew,
    stable_span_id,
)


def test_stable_tool_and_reserved_span_markers_build_in_order() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
    call_id = stable_span_id("read_file", 2)
    result = build_spans(
        (
            SpanMarker(call_id, SpanKind.CALL, SpanPhase.END, base + 2, root_pid=10),
            SpanMarker("startup", SpanKind.STARTUP, SpanPhase.END, base),
            SpanMarker(call_id, SpanKind.CALL, SpanPhase.START, base + 1, root_pid=10),
            SpanMarker("startup", SpanKind.STARTUP, SpanPhase.START, base - 1),
        )
    )

    assert call_id == "read_file+2"
    assert [span.span_id for span in result.spans] == ["startup", "read_file+2"]
    assert result.spans[1].root_pid == 10
    assert result.diagnostics == ()


def test_missing_duplicate_and_invalid_boundaries_remain_incomplete() -> None:
    result = build_spans(
        (
            SpanMarker("missing", SpanKind.IDLE, SpanPhase.START, 1.0),
            SpanMarker("invalid", SpanKind.CALL, SpanPhase.START, 3.0),
            SpanMarker("invalid", SpanKind.CALL, SpanPhase.END, 2.0),
        )
    )

    assert result.spans == ()
    assert result.diagnostics == ("INVALID_SPAN:invalid", "INCOMPLETE_SPAN:missing")


def test_clock_calibration_requires_multiple_samples() -> None:
    assert calibrated_skew((ClockSample(10.0, 11.0),)) is None
    assert (
        calibrated_skew(
            (
                ClockSample(10.0, 11.0),
                ClockSample(20.0, 21.2),
                ClockSample(30.0, 31.0),
            )
        )
        == 1.0
    )


def test_adjacent_boundary_belongs_to_next_span_only() -> None:
    result = build_spans(
        (
            SpanMarker("first", SpanKind.CALL, SpanPhase.START, 10.0),
            SpanMarker("first", SpanKind.CALL, SpanPhase.END, 11.0),
            SpanMarker("second", SpanKind.CALL, SpanPhase.START, 11.0),
            SpanMarker("second", SpanKind.CALL, SpanPhase.END, 12.0),
        )
    )

    attribution = attribute_event(11.0, None, AttributionContext(result.spans, ()))

    assert not attribution.ambiguous
    assert attribution.span_id == "second"
