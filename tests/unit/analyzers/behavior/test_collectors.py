from __future__ import annotations

from datetime import UTC, datetime, timedelta

from panopticon.analyzers.behavior.collectors import (
    AccessSemantics,
    AttributionContext,
    EvidenceSource,
    SpanBoundary,
    SpanKind,
    attribute_event,
    attribute_span,
    classify_access,
    collect_behavior,
    normalize_host,
    normalize_path,
)
from panopticon.sandbox.trace import TraceEvent


def event(
    operation: str,
    *,
    path: str | None = None,
    peer: str | None = None,
    pid: int = 10,
    timestamp: float = 100.0,
) -> TraceEvent:
    return TraceEvent(pid, timestamp, operation, operation, (), 0, path, None, peer)


def test_normalization_handles_paths_ipv4_ipv6_and_unix_sockets() -> None:
    assert normalize_path("/home/pano/project//a/../b") == "~/project/b"
    assert normalize_path("relative/file") == "/relative/file"
    assert normalize_host('sin_addr=inet_addr("192.0.2.1")') == "192.0.2.1"
    assert normalize_host('sin6_addr=inet_pton(AF_INET6, "2001:0db8::1")') == "2001:db8::1"
    assert normalize_host('{sa_family=AF_UNIX, sun_path="/tmp/pano.sock"}') == (
        "unix:/tmp/pano.sock"
    )
    assert normalize_host("Example.COM.:443") == "example.com"


def test_access_semantics_do_not_conflate_metadata_read_write_and_exec() -> None:
    assert classify_access(event("stat")) is AccessSemantics.METADATA
    assert classify_access(event("read")) is AccessSemantics.READ
    assert classify_access(event("write")) is AccessSemantics.WRITE
    assert classify_access(event("exec")) is AccessSemantics.EXECUTE
    assert classify_access(event("unknown")) is AccessSemantics.UNKNOWN


def test_collectors_merge_sources_deterministically_and_retain_coverage() -> None:
    trace = (
        event("write", path="/home/pano/z", timestamp=2.0),
        event("read", path="/home/pano/a", timestamp=1.0),
        event("read", path="/home/pano/a", timestamp=1.0),
        event("connect", peer='sin_addr=inet_addr("192.0.2.2")', timestamp=3.0),
        event("clone", timestamp=4.0),
    )

    first = collect_behavior(
        trace,
        snapshot=("/home/pano/new",),
        proxy=("Example.COM:443",),
        dns=("EXAMPLE.com.",),
        truncated=True,
    )
    second = collect_behavior(
        reversed(trace),
        snapshot=("/home/pano/new",),
        proxy=("Example.COM:443",),
        dns=("EXAMPLE.com.",),
        truncated=True,
    )

    assert first == second
    assert first.coverage.trace
    assert first.coverage.snapshot
    assert first.coverage.proxy
    assert first.coverage.dns
    assert first.coverage.partial
    assert first.diagnostics == ("TRUNCATED",)
    assert len([item for item in first.evidence if item.value == "~/a"]) == 1
    snapshot = next(item for item in first.evidence if item.source is EvidenceSource.SNAPSHOT)
    assert not snapshot.certainty


def test_span_attribution_uses_skew_process_tree_and_reserved_spans() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    call = SpanBoundary(
        "call-1",
        start,
        start + timedelta(seconds=2),
        SpanKind.CALL,
        root_pid=10,
    )
    startup = SpanBoundary(
        "startup",
        start - timedelta(seconds=2),
        start - timedelta(seconds=1),
        SpanKind.STARTUP,
    )
    context = AttributionContext((startup, call), ((11, 10),), skew=1.0)

    child = attribute_event(start.timestamp(), 11, context)
    unrelated = attribute_event(start.timestamp(), 99, context)
    reserved = attribute_event((start - timedelta(seconds=2)).timestamp(), 99, context)

    assert child.span_id == "call-1"
    assert child.reason_code == "ATTRIBUTED"
    assert unrelated.span_id is None
    assert reserved.span_id == "startup"


def test_equal_overlaps_are_ambiguous_instead_of_guessed() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    spans = (
        SpanBoundary("a", start, start + timedelta(seconds=2)),
        SpanBoundary("b", start, start + timedelta(seconds=2)),
    )
    context = AttributionContext(spans, ())

    attribution = attribute_event((start + timedelta(seconds=1)).timestamp(), None, context)

    assert attribution.ambiguous
    assert attribution.reason_code == "AMBIGUOUS_SPAN"
    assert attribution.span_id is None
    assert attribute_span((start + timedelta(seconds=1)).timestamp(), spans) is None
