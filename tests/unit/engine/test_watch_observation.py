from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from panopticon.analyzers.behavior.spans import SpanKind
from panopticon.discovery.base import DiscoveryEnv
from panopticon.engine.watch_behavior import apply_behavior_rules
from panopticon.engine.watch_events import convert_events
from panopticon.engine.watch_inventory import ProductionWatchInventory, WatchTargetContext
from panopticon.engine.watch_local_model import (
    LocalProtocol,
    LocalSpan,
    LocalTool,
    LocalWatchResult,
    LocalWatchStatus,
)
from panopticon.engine.watch_model import Coverage, TargetMode, TargetSelection
from panopticon.engine.watch_observation import build_watch_observation
from panopticon.engine.watch_observation_events import assigned_events
from panopticon.models.ids import derive_span_id
from panopticon.models.observation import DeclaredCompleteness
from panopticon.models.state import StageStatus
from panopticon.probe.argument_schema import JsonValue
from panopticon.probe.driver import CallStatus, DriverResult, DriverStatus, ToolCallResult
from panopticon.probe.protocol import MODERN_PROTOCOL, ProbeResult, ProbeStatus, ProtocolEra
from panopticon.sandbox.base import StreamResult
from panopticon.sandbox.decoy import generate_decoy_home
from panopticon.sandbox.netlog import NetworkEvent, NetworkLogSource
from panopticon.sandbox.trace_model import TraceEvent, TraceReason, TraceResult, TraceStatus

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
IMAGE = "ghcr.io/brnyxx/pano-sandbox-python:3.12@sha256:" + "a" * 64


def _context(tmp_path: Path) -> WatchTargetContext:
    return (
        ProductionWatchInventory(
            DiscoveryEnv(tmp_path, tmp_path, "darwin"),
            self_command=("python3", "/self/server.py"),
        )
        .select(TargetSelection(TargetMode.SELF))
        .contexts[0]
    )


def _result(
    tmp_path: Path,
    *,
    legacy: bool = False,
    outside: bool = False,
    early: bool = False,
    extra_spans: tuple[LocalSpan, ...] = (),
    trace_events: tuple[TraceEvent, ...] | None = None,
    network_events: tuple[NetworkEvent, ...] = (),
) -> LocalWatchResult:
    context = _context(tmp_path)
    manifest = generate_decoy_home("seed", str(context.target.installation_id))
    marker = manifest.markers[0]
    startup = LocalSpan(
        derive_span_id("startup", 0),
        "startup",
        0,
        NOW,
        NOW + timedelta(seconds=1),
        "0" * 16,
        "OK",
        SpanKind.STARTUP,
    )
    call = LocalSpan(
        derive_span_id("read_data", 1),
        "read_data",
        1,
        NOW + timedelta(seconds=1),
        NOW + timedelta(seconds=2),
        "1" * 16,
        "OK",
        SpanKind.CALL,
    )
    timestamp = (NOW + timedelta(seconds=3 if outside else 0.96 if early else 1.5)).timestamp()
    trace = TraceResult(
        trace_events
        or (
            TraceEvent(
                10,
                timestamp,
                "openat",
                "open",
                ("AT_FDCWD", '"/home/pano/.ssh/id_ed25519"', "O_RDONLY"),
                3,
                "/home/pano/.ssh/id_ed25519",
            ),
        ),
        TraceStatus.COMPLETE,
        TraceReason.COMPLETED,
    )
    response = ProbeResult(ProbeStatus.COMPLETE, "OK", {"value": marker.text})
    calls = DriverResult(
        DriverStatus.COMPLETE,
        "OK",
        (ToolCallResult("read_data", 1, CallStatus.COMPLETE, "OK", response),),
    )
    declaration: dict[str, JsonValue] = {
        "complete": True,
        "paths": ["~/.ssh/id_ed25519"],
        "hosts": [],
        "processes": [],
    }
    raw_tool: dict[str, JsonValue] = {
        "name": "read_data",
        "description": "Read ~/.ssh/id_ed25519",
        "inputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True},
        "_meta": {"panopticon": declaration},
    }
    coverage = {
        "file": Coverage.COMPLETE,
        "net": Coverage.COMPLETE,
        "process": Coverage.COMPLETE,
        "dns": Coverage.UNSUPPORTED,
        "proxy": Coverage.UNSUPPORTED,
        "snapshot": Coverage.UNKNOWN,
        "stdio": Coverage.COMPLETE,
    }
    era = ProtocolEra.LEGACY if legacy else ProtocolEra.MODERN
    return LocalWatchResult(
        context=context,
        status=LocalWatchStatus.COMPLETE,
        reason_code="OK",
        image=IMAGE,
        runtime="docker",
        offline=True,
        protocol=LocalProtocol(
            era,
            MODERN_PROTOCOL,
            "2024-11-05" if legacy else MODERN_PROTOCOL,
            legacy,
            "fixture",
            "1.0",
            ("tools",),
        ),
        tools=(LocalTool("read_data", "2" * 16, True, False, False),),
        raw_tools=(raw_tool,),
        calls=calls,
        spans=(startup, call, *extra_spans),
        trace=trace,
        stderr=StreamResult(b""),
        manifest=manifest,
        coverage=coverage,
        network_events=network_events,
    )


def _span(name: str, index: int, start: float, end: float, kind: SpanKind) -> LocalSpan:
    return LocalSpan(
        derive_span_id(name, index),
        name,
        index,
        NOW + timedelta(seconds=start),
        NOW + timedelta(seconds=end),
        f"{index:x}" * 16,
        "OK",
        kind,
    )


def test_annotated_file_and_exec_events_are_converted() -> None:
    events = convert_events(
        (
            TraceEvent(
                1,
                1.0,
                "openat",
                "open",
                ("AT_FDCWD", '"/home/pano/a"', "O_RDONLY"),
                3,
                "/home/pano/a",
            ),
            TraceEvent(
                1,
                1.1,
                "execve",
                "exec",
                ('"/bin/x"', '["/bin/x", "--ok"]'),
                0,
                "/bin/x",
            ),
        )
    )
    assert {event.root.kind for event in events} == {"file", "proc"}
    proc = next(event.root for event in events if event.root.kind == "proc")
    assert proc.argv == ("/bin/x", "--ok")


def test_observation_is_deterministic_declared_and_marker_redacted(tmp_path: Path) -> None:
    result = _result(tmp_path)

    first = build_watch_observation(result)
    second = build_watch_observation(result)

    assert first.observation is not None and first.observation == second.observation
    observation = first.observation
    assert observation.declared.completeness is DeclaredCompleteness.COMPLETE
    assert observation.state.overall.status is StageStatus.PARTIAL
    call = next(span for span in observation.spans if span.tool == "read_data")
    assert {event.root.kind for event in call.events} == {"file", "leak"}
    file_event = next(event.root for event in call.events if event.root.kind == "file")
    assert file_event.decoy and file_event.decoy_key
    assert result.manifest is not None
    assert result.manifest.markers[0].text not in observation.model_dump_json()
    behavior = apply_behavior_rules(result, first)
    assert behavior is not None
    assert "WATCH-001" in {finding.rule_id for finding in behavior.observation.findings}
    assert result.manifest.markers[0].text not in behavior.observation.model_dump_json()


def test_unassigned_events_and_legacy_fallback_remain_visible(tmp_path: Path) -> None:
    build = build_watch_observation(_result(tmp_path, legacy=True, outside=True))

    assert build.observation is not None
    assert build.uncovered_events == 1
    assert "UNATTRIBUTED_EVENTS" in build.diagnostics
    assert build.observation.protocol.era.value == "legacy"
    assert build.observation.state.stages.version_discovery.status is StageStatus.PARTIAL
    assert build.observation.state.stages.handshake.status is StageStatus.COMPLETE


def test_call_events_allow_bounded_clock_skew(tmp_path: Path) -> None:
    build = build_watch_observation(_result(tmp_path, early=True))

    assert build.observation is not None
    call = next(span for span in build.observation.spans if span.tool == "read_data")
    assert any(event.root.kind == "file" for event in call.events)


def test_event_attribution_prefers_exact_idle_and_tolerates_call_skew(tmp_path: Path) -> None:
    idle = _span("idle", 2, 2.0, 3.0, SpanKind.IDLE)
    events = (
        TraceEvent(
            10, (NOW + timedelta(seconds=2.5)).timestamp(), "openat", "open", (), 3, "/idle"
        ),
        TraceEvent(
            10, (NOW + timedelta(seconds=0.96)).timestamp(), "openat", "open", (), 3, "/call"
        ),
    )
    result = _result(tmp_path, extra_spans=(idle,), trace_events=events)
    assigned, uncovered = assigned_events(result)

    assert uncovered == 0
    assert [event.path for event in assigned[idle.span_id]] == ["/idle"]
    call_id = derive_span_id("read_data", 1)
    assert [event.path for event in assigned[call_id]] == ["/call"]


def test_event_attribution_falls_back_to_startup_then_session(tmp_path: Path) -> None:
    session = _span("session", 3, -1.0, 4.0, SpanKind.SESSION)
    events = (
        TraceEvent(
            10, (NOW + timedelta(seconds=0.5)).timestamp(), "openat", "open", (), 3, "/startup"
        ),
        TraceEvent(
            10, (NOW - timedelta(seconds=0.5)).timestamp(), "openat", "open", (), 3, "/session"
        ),
    )
    assigned, uncovered = assigned_events(
        _result(tmp_path, extra_spans=(session,), trace_events=events)
    )

    assert uncovered == 0
    assert assigned[derive_span_id("startup", 0)][0].path == "/startup"
    assert assigned[session.span_id][0].path == "/session"


def test_timed_network_events_are_attributed_to_call_idle_and_session(tmp_path: Path) -> None:
    idle = _span("idle", 2, 2.0, 3.0, SpanKind.IDLE)
    session = _span("session", 3, -1.0, 4.0, SpanKind.SESSION)
    network = tuple(
        NetworkEvent(NetworkLogSource.DNS, host, timestamp=NOW + timedelta(seconds=offset))
        for host, offset in (("call.example", 1.5), ("idle.example", 2.5), ("session.example", 3.5))
    )
    build = build_watch_observation(
        _result(tmp_path, extra_spans=(idle, session), network_events=network)
    )

    assert build.observation is not None
    by_tool = {span.tool: span for span in build.observation.spans}
    assert [
        event.root.host for event in by_tool["read_data"].events if event.root.kind == "net"
    ] == ["call.example"]
    assert [event.root.host for event in by_tool["idle"].events if event.root.kind == "net"] == [
        "idle.example"
    ]
    assert [event.root.host for event in by_tool["session"].events if event.root.kind == "net"] == [
        "session.example"
    ]


def test_timestamp_less_network_event_uses_first_session(tmp_path: Path) -> None:
    session = _span("session", 3, -1.0, 4.0, SpanKind.SESSION)
    event = NetworkEvent(NetworkLogSource.PROXY, "fallback.example", port=443)
    build = build_watch_observation(
        _result(tmp_path, extra_spans=(session,), network_events=(event,))
    )

    assert build.observation is not None
    span = next(span for span in build.observation.spans if span.tool == "session")
    assert [item.root.host for item in span.events if item.root.kind == "net"] == [
        "fallback.example"
    ]


def test_event_outside_all_spans_is_uncovered(tmp_path: Path) -> None:
    event = TraceEvent(
        10, (NOW + timedelta(seconds=10)).timestamp(), "openat", "open", (), 3, "/outside"
    )
    assigned, uncovered = assigned_events(_result(tmp_path, trace_events=(event,)))

    assert uncovered == 1
    assert all(not events for events in assigned.values())
