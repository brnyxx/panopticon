"""Collection phase for production local watch sessions."""

from __future__ import annotations

import asyncio
from datetime import datetime

from panopticon.analyzers.behavior.spans import SpanKind
from panopticon.probe.argument_schema import JsonValue
from panopticon.probe.client import McpClient
from panopticon.probe.driver import CallDriver, DriverStatus
from panopticon.probe.protocol import ProbeStatus
from panopticon.sandbox.base import Container, InteractiveSession
from panopticon.sandbox.decoy import DecoyManifest
from panopticon.sandbox.snapshot import collect_home, diff_snapshots
from panopticon.sandbox.trace import parse_strace
from panopticon.sandbox.trace_model import TraceEvent, TraceStatus

from .watch_inventory import WatchTargetContext
from .watch_local_evidence import (
    Clock,
    SpanRecorder,
    local_protocol,
    normalize_tools,
    reserved_span,
)
from .watch_local_model import LocalSpan, LocalWatchResult, LocalWatchStatus
from .watch_local_runtime import bounded_stderr
from .watch_model import Coverage, WatchOptions


async def collect_local_session(
    context: WatchTargetContext,
    options: WatchOptions,
    *,
    runtime_name: str,
    image: str,
    manifest: DecoyManifest,
    client: McpClient,
    container: Container,
    session: InteractiveSession,
    startup_started: datetime,
    clock: Clock,
    overrides: dict[str, dict[str, JsonValue]],
) -> LocalWatchResult:
    initialized = await client.initialize(timeout=options.timeout)
    if initialized.status is not ProbeStatus.COMPLETE:
        status = (
            LocalWatchStatus.UNSUPPORTED
            if initialized.status is ProbeStatus.UNSUPPORTED
            else LocalWatchStatus.INCOMPLETE
        )
        return LocalWatchResult(
            context,
            status,
            initialized.reason_code,
            image=image,
            runtime=runtime_name,
            offline=options.offline,
        )
    listed = await client.list_paginated("tools/list", timeout=options.timeout)
    if listed.status not in {ProbeStatus.COMPLETE, ProbeStatus.UNSUPPORTED}:
        return LocalWatchResult(
            context,
            LocalWatchStatus.INCOMPLETE,
            listed.reason_code,
            image=image,
            runtime=runtime_name,
            offline=options.offline,
        )
    values = listed.result.get("tools", []) if isinstance(listed.result, dict) else []
    raw_tools, tools = normalize_tools(values)
    startup = reserved_span("startup", SpanKind.STARTUP, startup_started, clock.now())
    recorder = SpanRecorder(clock)
    snapshot_before = await collect_home(container, timeout=min(options.timeout, 2.0))
    calls = await CallDriver(
        client,
        calls=options.calls,
        stage_timeout=options.timeout,
        total_timeout=max(options.timeout, options.timeout * max(1, options.calls)),
        allow_destructive=options.allow_destructive,
        observer=recorder,
    ).run(raw_tools, overrides=overrides)
    idle_span: tuple[LocalSpan, ...] = ()
    if options.idle:
        idle_started = clock.now()
        await asyncio.sleep(options.idle)
        idle_span = (reserved_span("idle", SpanKind.IDLE, idle_started, clock.now()),)
    trace = parse_strace((await container.trace()).data.decode(errors="replace"))
    snapshot_after = await collect_home(container, timeout=min(options.timeout, 2.0))
    snapshot_diff = (
        diff_snapshots(snapshot_before, snapshot_after)
        if snapshot_before is not None and snapshot_after is not None
        else None
    )
    if snapshot_diff is not None and snapshot_diff.paths:
        now = clock.now().timestamp()
        events = tuple(
            TraceEvent(
                pid=0,
                timestamp=now,
                syscall="snapshot",
                operation=operation,
                arguments=(),
                result=0,
                path=path,
            )
            for operation, path in snapshot_diff.paths
        )
        trace = type(trace)(
            events=(*trace.events, *events),
            status=trace.status,
            reason=trace.reason,
            diagnostics=trace.diagnostics,
        )
    stderr = await bounded_stderr(session)
    session_span = reserved_span("session", SpanKind.SESSION, startup_started, clock.now())
    complete = (
        calls.status is DriverStatus.COMPLETE
        and trace.status is TraceStatus.COMPLETE
        and not client.notifications_truncated
    )
    status = LocalWatchStatus.COMPLETE if complete else LocalWatchStatus.PARTIAL
    coverage = {
        "file": Coverage.COMPLETE if trace.status is TraceStatus.COMPLETE else Coverage.UNKNOWN,
        "process": Coverage.COMPLETE if trace.status is TraceStatus.COMPLETE else Coverage.UNKNOWN,
        "net": Coverage.COMPLETE if trace.status is TraceStatus.COMPLETE else Coverage.UNKNOWN,
        "stdio": Coverage.UNKNOWN if client.notifications_truncated else Coverage.COMPLETE,
        "dns": Coverage.UNSUPPORTED if options.offline else Coverage.UNKNOWN,
        "proxy": Coverage.UNSUPPORTED if options.offline else Coverage.UNKNOWN,
        "snapshot": Coverage.COMPLETE if snapshot_diff is not None else Coverage.UNKNOWN,
    }
    return LocalWatchResult(
        context=context,
        status=status,
        reason_code=calls.reason_code if complete else "PARTIAL_COVERAGE",
        image=image,
        runtime=runtime_name,
        offline=options.offline,
        protocol=local_protocol(client),
        tools=tools,
        raw_tools=raw_tools,
        calls=calls,
        spans=(session_span, startup, *recorder.spans, *idle_span),
        trace=trace,
        stderr=stderr,
        notifications=client.notifications,
        manifest=manifest,
        coverage=coverage,
        diagnostics=trace.diagnostics,
        snapshot=snapshot_diff,
    )


__all__ = ["collect_local_session"]
