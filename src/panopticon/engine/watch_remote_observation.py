"""Build remote persisted observations and apply WATCH rules."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal

from pydantic import AnyHttpUrl

from panopticon import __version__
from panopticon.models.ids import ObservationId, SpanId
from panopticon.models.inventory import Transport
from panopticon.models.observation import (
    DiscoveryReason,
    FallbackReason,
    Observation,
    ProtocolInfo,
    RemoteSandbox,
    ServerInfo,
    Span,
    SpanResult,
    ToolAnnotations,
    ToolInfo,
)
from panopticon.models.observation import ProtocolEra as ObservationEra
from panopticon.probe.argument_schema import JsonValue
from panopticon.probe.driver import DriverResult
from panopticon.probe.protocol import ProtocolEra
from panopticon.sandbox.decoy import DecoyManifest

from .watch_behavior import apply_behavior_rules
from .watch_declared import build_declared
from .watch_inventory import WatchTargetContext
from .watch_local_model import (
    LocalProtocol,
    LocalSpan,
    LocalTool,
    LocalWatchResult,
    LocalWatchStatus,
)
from .watch_model import Coverage as WatchCoverage
from .watch_observation import WatchObservationBuild
from .watch_remote_events import Exchange, events_by_span
from .watch_state import build_state


def build_remote_observation(
    context: WatchTargetContext,
    status: LocalWatchStatus,
    protocol: LocalProtocol,
    tools: tuple[LocalTool, ...],
    raw_tools: tuple[dict[str, JsonValue], ...],
    calls: DriverResult,
    spans: tuple[LocalSpan, ...],
    manifest: DecoyManifest,
    coverage: Mapping[str, WatchCoverage],
    exchanges: tuple[Exchange, ...],
    endpoint: str,
    observed_at: datetime,
) -> Observation:
    synthetic = LocalWatchResult(
        context=context,
        status=status,
        reason_code=calls.reason_code,
        offline=False,
        protocol=protocol,
        tools=tools,
        raw_tools=raw_tools,
        calls=calls,
        spans=spans,
        manifest=manifest,
        coverage=coverage,
    )
    declaration = build_declared(synthetic)
    state = build_state(synthetic, declaration.persisted.completeness, uncovered_events=0)
    exchange_events = events_by_span(exchanges, spans, manifest)
    persisted_spans = tuple(
        Span(
            span_id=SpanId(span.span_id),
            tool=span.tool,
            call_index=span.call_index,
            args_fingerprint=span.args_fingerprint,
            result=SpanResult.OK,
            duration_ms=max(0, int((span.ended_at - span.started_at).total_seconds() * 1000)),
            events=exchange_events.get(span.span_id, ()),
        )
        for span in spans
    )
    observed = observed_at.astimezone(UTC)
    semantic = f"{context.target.installation_id}:{observed.isoformat()}"
    transport: Literal["sse", "streamable_http"] = (
        "sse" if context.target.transport is Transport.SSE else "streamable_http"
    )
    observation = Observation(
        schema_version="1.0",
        observation_id=ObservationId(f"obs_{hashlib.sha256(semantic.encode()).hexdigest()[:24]}"),
        server_id=context.target.server_id,
        installation_id=context.target.installation_id,
        observed_at=observed,
        pano_version=__version__,
        sandbox=RemoteSandbox(
            runtime="remote",
            transport=transport,
            endpoint=AnyHttpUrl(endpoint),
        ),
        package_resolved=None,
        protocol=ProtocolInfo(
            era=ObservationEra(protocol.era.value),
            requested_version=protocol.requested_version,
            selected_version=protocol.selected_version,
            discovery_reason=(
                DiscoveryReason.MODERN_METADATA
                if protocol.era is ProtocolEra.MODERN
                else DiscoveryReason.LEGACY_HANDSHAKE
            ),
            fallback_reason=(
                FallbackReason.LEGACY_REQUIRED if protocol.fallback else FallbackReason.NONE
            ),
            server_info=ServerInfo(name=protocol.server_name, version=protocol.server_version),
            capabilities=protocol.capabilities,
        ),
        tools=tuple(
            ToolInfo(
                name=tool.name,
                input_schema_hash=tool.input_schema_hash,
                annotations=ToolAnnotations(
                    read_only=tool.read_only,
                    destructive=tool.destructive,
                    open_world=tool.open_world,
                ),
            )
            for tool in tools
        ),
        spans=persisted_spans,
        declared=declaration.persisted,
        findings=(),
        state=state,
    )
    behavior = apply_behavior_rules(
        synthetic,
        WatchObservationBuild(observation, 0, declared_scope=declaration.scope),
    )
    return behavior.observation if behavior is not None else observation


__all__ = ["build_remote_observation"]
