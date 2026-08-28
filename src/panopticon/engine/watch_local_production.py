"""Production local stdio watch session orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

from panopticon.analyzers.behavior.spans import SpanKind
from panopticon.models.inventory import Transport
from panopticon.probe.client import McpClient
from panopticon.probe.driver import CallDriver, DriverStatus
from panopticon.probe.protocol import ProbeStatus
from panopticon.sandbox.base import (
    Container,
    ContainerSpec,
    InteractiveSession,
    SandboxError,
)
from panopticon.sandbox.decoy import decoy_archive, generate_decoy_home
from panopticon.sandbox.image_catalog import DEFAULT_IMAGE_CATALOG, ImageCatalog
from panopticon.sandbox.network import NetworkController, NetworkServices, NetworkSession
from panopticon.sandbox.trace import parse_strace
from panopticon.sandbox.trace_model import TraceStatus

from .watch_inventory import WatchTargetContext
from .watch_local_evidence import (
    Clock,
    SpanRecorder,
    SystemClock,
    argument_overrides,
    image_reference,
    local_protocol,
    normalize_tools,
    reserved_span,
    target_environment,
)
from .watch_local_model import LocalSpan, LocalWatchResult, LocalWatchStatus
from .watch_local_runtime import LocalRuntime, bounded_stderr, cleanup_local, unsupported
from .watch_model import Coverage, WatchOptions


async def run_local_production(
    context: WatchTargetContext,
    options: WatchOptions,
    *,
    runtime: LocalRuntime,
    catalog: ImageCatalog = DEFAULT_IMAGE_CATALOG,
    real_env: Mapping[str, str] | None = None,
    self_source: Path | None = None,
    network: NetworkController | None = None,
    rootless: bool = False,
    clock: Clock | None = None,
) -> LocalWatchResult:
    target = context.target
    if target.transport is not Transport.STDIO or target.command is None:
        return unsupported(context, "UNSUPPORTED_LOCAL_COMMAND")
    image = image_reference(context, catalog, self_source)
    if image is None:
        return unsupported(context, "UNSUPPORTED_IMAGE")
    if not runtime.available():
        return unsupported(context, "RUNTIME_UNAVAILABLE")
    try:
        overrides = argument_overrides(options.args)
    except ValueError:
        return LocalWatchResult(
            context,
            LocalWatchStatus.INCOMPLETE,
            "ARG_OVERRIDE_INVALID",
            image=image,
            runtime=runtime.name,
            offline=options.offline,
        )
    manifest = generate_decoy_home(str(target.installation_id), str(target.installation_id))
    environment = target_environment(context, manifest.env, options, real_env)
    first_file = sorted(manifest.files)[0]
    environment["PANO_DECOY_FILE"] = f"/home/pano/{first_file}"
    environment["PANO_DECOY_VALUE"] = manifest.markers[0].text
    controller = network
    session_clock = clock or SystemClock()
    startup_started = session_clock.now()
    network_session: NetworkSession | None = None
    container: Container | None = None
    session: InteractiveSession | None = None
    client: McpClient | None = None
    result: LocalWatchResult
    try:
        if not options.offline:
            await runtime.pull(image)
            controller = controller or NetworkController(runtime.executable)
        spec = ContainerSpec(
            image,
            [target.command, *target.args],
            environment,
            decoy_archive(manifest),
            self_source=self_source,
        )
        if controller is not None and not options.offline:
            network_session = await controller.start(
                NetworkServices(image, f"pano-{str(target.installation_id)[:24]}", rootless)
            )
            spec = network_session.apply(spec)
        container = await runtime.run(spec)
        session = await container.open_stdio()
        client = McpClient(session.reader, session.writer, timeout=options.timeout)
        initialized = await client.initialize(timeout=options.timeout)
        if initialized.status is not ProbeStatus.COMPLETE:
            status = (
                LocalWatchStatus.UNSUPPORTED
                if initialized.status is ProbeStatus.UNSUPPORTED
                else LocalWatchStatus.INCOMPLETE
            )
            result = LocalWatchResult(
                context,
                status,
                initialized.reason_code,
                image=image,
                runtime=runtime.name,
                offline=options.offline,
            )
        else:
            listed = await client.list_paginated("tools/list", timeout=options.timeout)
            if listed.status not in {ProbeStatus.COMPLETE, ProbeStatus.UNSUPPORTED}:
                result = LocalWatchResult(
                    context,
                    LocalWatchStatus.INCOMPLETE,
                    listed.reason_code,
                    image=image,
                    runtime=runtime.name,
                    offline=options.offline,
                )
            else:
                values = listed.result.get("tools", []) if isinstance(listed.result, dict) else []
                raw_tools, tools = normalize_tools(values)
                startup = reserved_span(
                    "startup",
                    SpanKind.STARTUP,
                    startup_started,
                    session_clock.now(),
                )
                recorder = SpanRecorder(session_clock)
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
                    idle_started = session_clock.now()
                    await asyncio.sleep(options.idle)
                    idle_span = (
                        reserved_span(
                            "idle",
                            SpanKind.IDLE,
                            idle_started,
                            session_clock.now(),
                        ),
                    )
                trace = parse_strace((await container.trace()).data.decode(errors="replace"))
                stderr = await bounded_stderr(session)
                session_span = reserved_span(
                    "session",
                    SpanKind.SESSION,
                    startup_started,
                    session_clock.now(),
                )
                complete = (
                    calls.status is DriverStatus.COMPLETE
                    and trace.status is TraceStatus.COMPLETE
                    and not client.notifications_truncated
                )
                status = LocalWatchStatus.COMPLETE if complete else LocalWatchStatus.PARTIAL
                coverage = {
                    "file": (
                        Coverage.COMPLETE
                        if trace.status is TraceStatus.COMPLETE
                        else Coverage.UNKNOWN
                    ),
                    "process": (
                        Coverage.COMPLETE
                        if trace.status is TraceStatus.COMPLETE
                        else Coverage.UNKNOWN
                    ),
                    "net": (
                        Coverage.COMPLETE
                        if trace.status is TraceStatus.COMPLETE
                        else Coverage.UNKNOWN
                    ),
                    "stdio": (
                        Coverage.UNKNOWN if client.notifications_truncated else Coverage.COMPLETE
                    ),
                    "dns": Coverage.UNSUPPORTED if options.offline else Coverage.UNKNOWN,
                    "proxy": Coverage.UNSUPPORTED if options.offline else Coverage.UNKNOWN,
                    "snapshot": Coverage.UNKNOWN,
                }
                result = LocalWatchResult(
                    context=context,
                    status=status,
                    reason_code=calls.reason_code if complete else "PARTIAL_COVERAGE",
                    image=image,
                    runtime=runtime.name,
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
                )
    except asyncio.CancelledError:
        cleanup = asyncio.create_task(
            cleanup_local(client, session, container, controller, network_session)
        )
        await asyncio.shield(cleanup)
        raise
    except (OSError, SandboxError, TimeoutError) as error:
        reason = str(error) if isinstance(error, SandboxError) else "LOCAL_RUNTIME_FAILED"
        result = LocalWatchResult(
            context,
            LocalWatchStatus.INCOMPLETE,
            reason,
            image=image,
            runtime=runtime.name,
            offline=options.offline,
        )
    except BaseException:
        cleanup = asyncio.create_task(
            cleanup_local(client, session, container, controller, network_session)
        )
        await asyncio.shield(cleanup)
        raise
    cleanup_diagnostics = await cleanup_local(
        client, session, container, controller, network_session
    )
    if cleanup_diagnostics:
        return LocalWatchResult(
            context,
            LocalWatchStatus.INCOMPLETE,
            "CLEANUP_FAILED",
            image=image,
            runtime=runtime.name,
            offline=options.offline,
            diagnostics=cleanup_diagnostics,
        )
    return result


__all__ = ["LocalRuntime", "run_local_production"]
