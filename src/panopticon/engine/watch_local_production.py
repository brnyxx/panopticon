"""Production local stdio watch session orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from panopticon.models.inventory import Transport
from panopticon.probe.client import McpClient
from panopticon.sandbox.base import Container, ContainerSpec, InteractiveSession, SandboxError
from panopticon.sandbox.decoy import decoy_archive, generate_decoy_home
from panopticon.sandbox.image_catalog import DEFAULT_IMAGE_CATALOG, ImageCatalog
from panopticon.sandbox.netlog import NetworkLogStatus
from panopticon.sandbox.network import NetworkController, NetworkServices, NetworkSession

from .watch_inventory import WatchTargetContext
from .watch_local_collect import collect_local_session
from .watch_local_evidence import (
    Clock,
    SystemClock,
    argument_overrides,
    image_reference,
    target_environment,
)
from .watch_local_model import LocalWatchResult, LocalWatchStatus
from .watch_local_runtime import LocalRuntime, cleanup_local, unsupported
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
    project_filenames = context.raw_entry.metadata.get(
        "project_filenames", context.raw_entry.raw.get("project_filenames", ())
    )
    names = (
        tuple(name for name in project_filenames if isinstance(name, str))
        if isinstance(project_filenames, (list, tuple))
        else ()
    )
    if not isinstance(project_filenames, (list, tuple)) or len(names) != len(project_filenames):
        names = ()
    manifest = generate_decoy_home(
        str(target.installation_id),
        str(target.installation_id),
        project_filenames=names,
    )
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
        result = await collect_local_session(
            context,
            options,
            runtime_name=runtime.name,
            image=image,
            manifest=manifest,
            client=client,
            container=container,
            session=session,
            startup_started=startup_started,
            clock=session_clock,
            overrides=overrides,
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
    if network_session is not None and controller is not None:
        try:
            logs = await controller.collect_logs(network_session)
            events = (*logs.dns.events, *logs.proxy.events, *logs.blocked_egress.events)
            diagnostics = (
                *tuple(
                    f"NETWORK_{source}_{item}"
                    for source, parsed in (("DNS", logs.dns), ("PROXY", logs.proxy))
                    for item in parsed.diagnostics
                ),
                "DIRECT_EGRESS_UNKNOWN",
            )
            result = replace(
                result,
                status=(
                    result.status
                    if logs.dns.status is NetworkLogStatus.COMPLETE
                    and logs.proxy.status is NetworkLogStatus.COMPLETE
                    else LocalWatchStatus.PARTIAL
                ),
                reason_code=(
                    result.reason_code
                    if logs.dns.status is NetworkLogStatus.COMPLETE
                    and logs.proxy.status is NetworkLogStatus.COMPLETE
                    else "PARTIAL_COVERAGE"
                ),
                network_events=events,
                diagnostics=(*result.diagnostics, *diagnostics),
                coverage={
                    **result.coverage,
                    "dns": Coverage.COMPLETE
                    if logs.dns.status is NetworkLogStatus.COMPLETE
                    else Coverage.UNKNOWN,
                    "proxy": Coverage.COMPLETE
                    if logs.proxy.status is NetworkLogStatus.COMPLETE
                    else Coverage.UNKNOWN,
                },
            )
        except (OSError, SandboxError):
            result = replace(
                result,
                diagnostics=(
                    *result.diagnostics,
                    "NETWORK_LOGS_UNAVAILABLE",
                    "DIRECT_EGRESS_UNKNOWN",
                ),
            )
    elif options.offline:
        result = replace(result, diagnostics=(*result.diagnostics, "DIRECT_EGRESS_UNKNOWN"))
    cleanup_diagnostics = await cleanup_local(
        client, session, container, controller, network_session
    )
    if cleanup_diagnostics:
        return replace(
            result,
            status=LocalWatchStatus.INCOMPLETE,
            reason_code="CLEANUP_FAILED",
            diagnostics=(*result.diagnostics, *cleanup_diagnostics),
        )
    return result


__all__ = ["LocalRuntime", "run_local_production"]
