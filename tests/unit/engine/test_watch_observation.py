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
from panopticon.models.ids import derive_span_id
from panopticon.models.observation import DeclaredCompleteness
from panopticon.models.state import StageStatus
from panopticon.probe.argument_schema import JsonValue
from panopticon.probe.driver import CallStatus, DriverResult, DriverStatus, ToolCallResult
from panopticon.probe.protocol import MODERN_PROTOCOL, ProbeResult, ProbeStatus, ProtocolEra
from panopticon.sandbox.base import StreamResult
from panopticon.sandbox.decoy import generate_decoy_home
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


def _result(tmp_path: Path, *, legacy: bool = False, outside: bool = False) -> LocalWatchResult:
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
    timestamp = (NOW + timedelta(seconds=3 if outside else 1.5)).timestamp()
    trace = TraceResult(
        (
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
        spans=(startup, call),
        trace=trace,
        stderr=StreamResult(b""),
        manifest=manifest,
        coverage=coverage,
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
