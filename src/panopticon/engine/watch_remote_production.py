"""Production remote MCP orchestration over instrumented HTTP requests."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from panopticon.analyzers.behavior.spans import SpanKind
from panopticon.models.inventory import Transport
from panopticon.models.observation import Observation
from panopticon.probe.driver import CallDriver, DriverStatus
from panopticon.probe.http import StreamableHttpClient
from panopticon.probe.protocol import LEGACY_PROTOCOL, MODERN_PROTOCOL, ProbeStatus, ProtocolEra
from panopticon.probe.remote_security import Resolver, validate_url
from panopticon.sandbox.decoy import generate_decoy_home

from .watch_inventory import WatchTargetContext
from .watch_local_evidence import (
    SpanRecorder,
    SystemClock,
    argument_overrides,
    normalize_tools,
    reserved_span,
)
from .watch_local_model import LocalProtocol, LocalWatchStatus
from .watch_model import Coverage as WatchCoverage
from .watch_model import WatchOptions
from .watch_remote_events import ExchangeRecorder, SystemResolver, request_headers
from .watch_remote_observation import build_remote_observation


@dataclass(frozen=True, slots=True)
class RemoteWatchResult:
    status: LocalWatchStatus
    reason_code: str
    observation: Observation | None = None
    secrets: tuple[str, ...] = field(default=(), repr=False)
    diagnostics: tuple[str, ...] = ()


async def run_remote_production(
    context: WatchTargetContext,
    options: WatchOptions,
    *,
    resolver: Resolver | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    run_identity: str | None = None,
) -> RemoteWatchResult:
    target = context.target
    if target.transport not in {Transport.HTTP, Transport.SSE} or target.url is None:
        return RemoteWatchResult(LocalWatchStatus.UNSUPPORTED, "UNSUPPORTED_TRANSPORT")
    if options.offline:
        return RemoteWatchResult(LocalWatchStatus.UNSUPPORTED, "OFFLINE")
    try:
        decision = validate_url(str(target.url), resolver or SystemResolver())
    except OSError:
        return RemoteWatchResult(LocalWatchStatus.INCOMPLETE, "DNS_FAILED")
    if not decision.allowed:
        return RemoteWatchResult(LocalWatchStatus.UNSUPPORTED, decision.reason)
    manifest = generate_decoy_home(
        str(target.installation_id),
        run_identity or os.urandom(8).hex(),
    )
    headers, secrets = request_headers(
        context,
        options,
        tuple(marker.text for marker in manifest.markers),
    )
    recorder = ExchangeRecorder()
    async with httpx.AsyncClient(
        trust_env=False,
        follow_redirects=False,
        timeout=httpx.Timeout(options.timeout),
        transport=transport,
        event_hooks={"request": [recorder.request], "response": [recorder.response]},
    ) as http:
        client = StreamableHttpClient(
            decision.url,
            http,
            timeout=options.timeout,
            headers=headers,
            resolver=resolver or SystemResolver(),
        )
        clock = SystemClock()
        session_started = clock.now()
        try:
            initialized = await client.initialize()
            if initialized.status is not ProbeStatus.COMPLETE:
                status = (
                    LocalWatchStatus.UNSUPPORTED
                    if initialized.status is ProbeStatus.UNSUPPORTED
                    else LocalWatchStatus.INCOMPLETE
                )
                return RemoteWatchResult(status, initialized.reason_code, secrets=secrets)
            listed = await client.list_paginated("tools/list", timeout=options.timeout)
            if listed.status not in {ProbeStatus.COMPLETE, ProbeStatus.UNSUPPORTED}:
                return RemoteWatchResult(
                    LocalWatchStatus.INCOMPLETE, listed.reason_code, secrets=secrets
                )
            values = listed.result.get("tools", []) if isinstance(listed.result, dict) else []
            raw_tools, tools = normalize_tools(values)
            span_recorder = SpanRecorder(clock)
            try:
                overrides = argument_overrides(options.args)
            except ValueError:
                return RemoteWatchResult(
                    LocalWatchStatus.INCOMPLETE, "ARG_OVERRIDE_INVALID", secrets=secrets
                )
            calls = await CallDriver(
                client,
                calls=options.calls,
                stage_timeout=options.timeout,
                allow_destructive=options.allow_destructive,
                observer=span_recorder,
            ).run(raw_tools, overrides=overrides)
            session_ended = clock.now()
        finally:
            await client.close()
    spans = (
        reserved_span("session", SpanKind.SESSION, session_started, session_ended),
        *span_recorder.spans,
    )
    era = client.era or ProtocolEra.MODERN
    protocol = LocalProtocol(
        era,
        MODERN_PROTOCOL,
        MODERN_PROTOCOL if era is ProtocolEra.MODERN else LEGACY_PROTOCOL,
        era is ProtocolEra.LEGACY,
        str(client.server_info.get("name") or "unknown"),
        str(client.server_info.get("version") or "unknown"),
        tuple(sorted(client.capabilities)),
    )
    status = (
        LocalWatchStatus.COMPLETE
        if calls.status is DriverStatus.COMPLETE
        else LocalWatchStatus.PARTIAL
    )
    coverage = {
        "file": WatchCoverage.UNSUPPORTED,
        "net": WatchCoverage.COMPLETE,
        "process": WatchCoverage.UNSUPPORTED,
        "dns": WatchCoverage.COMPLETE,
        "proxy": WatchCoverage.UNSUPPORTED,
        "snapshot": WatchCoverage.UNSUPPORTED,
        "stdio": WatchCoverage.UNSUPPORTED,
    }
    observation = build_remote_observation(
        context,
        status,
        protocol,
        tools,
        raw_tools,
        calls,
        spans,
        manifest,
        coverage,
        tuple(recorder.exchanges),
        decision.url,
        session_started,
    )
    return RemoteWatchResult(status, calls.reason_code, observation, secrets)


__all__ = ["RemoteWatchResult", "run_remote_production"]
