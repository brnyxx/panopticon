"""Build strict persisted observations from completed local watch evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from panopticon import __version__
from panopticon.declared.model import DeclaredScope
from panopticon.models.ids import ObservationId
from panopticon.models.observation import (
    DiscoveryReason,
    FallbackReason,
    LocalSandbox,
    Observation,
    ProtocolEra,
    ProtocolInfo,
    ServerInfo,
    ToolAnnotations,
    ToolInfo,
)
from panopticon.sandbox.noise import DEFAULT_NOISE_POLICY

from .watch_declared import build_declared
from .watch_local_model import LocalWatchResult
from .watch_observation_events import assigned_events, build_observation_events, decoy_paths
from .watch_state import build_state


@dataclass(frozen=True, slots=True)
class WatchObservationBuild:
    observation: Observation | None
    uncovered_events: int
    diagnostics: tuple[str, ...] = ()
    declared_scope: DeclaredScope | None = None
    reason_code: str = "OK"
    filtered_events: int = 0


def _observation_id(result: LocalWatchResult, observed_at: datetime) -> ObservationId:
    trace = tuple(
        (event.pid, event.timestamp, event.syscall, event.operation, event.path, event.peer)
        for event in (result.trace.events if result.trace is not None else ())
    )
    semantic = (
        str(result.context.target.installation_id),
        observed_at.isoformat(),
        result.status.value,
        result.reason_code,
        trace,
    )
    encoded = json.dumps(semantic, sort_keys=True, separators=(",", ":"))
    return ObservationId(f"obs_{hashlib.sha256(encoded.encode()).hexdigest()[:24]}")


def build_watch_observation(
    result: LocalWatchResult,
    *,
    observed_at: datetime | None = None,
    tracer: str = "strace",
    raw: bool = False,
) -> WatchObservationBuild:
    protocol = result.protocol
    image = result.image
    runtime = result.runtime
    if (
        protocol is None
        or image is None
        or runtime not in {"docker", "podman"}
        or result.trace is None
        or result.manifest is None
        or not result.spans
    ):
        return WatchObservationBuild(None, 0, result.diagnostics, reason_code="EVIDENCE_INCOMPLETE")
    observed = observed_at or min(span.started_at for span in result.spans)
    if observed.tzinfo is None:
        return WatchObservationBuild(None, 0, result.diagnostics, reason_code="TIMEZONE_REQUIRED")
    observed = observed.astimezone(UTC)
    trace_events, filtered_count = DEFAULT_NOISE_POLICY.filter(result.trace.events, raw=raw)
    assigned, uncovered = assigned_events(result, trace_events)
    decoys = decoy_paths(result)
    spans = build_observation_events(result, assigned, decoys)
    declaration = build_declared(result)
    state = build_state(result, declaration.persisted.completeness, uncovered_events=uncovered)
    image_name, image_digest = image.rsplit("@", 1)
    runtime_name = cast(Literal["docker", "podman"], runtime)
    package = result.context.target.package
    observation = Observation(
        schema_version="1.0",
        observation_id=_observation_id(result, observed),
        server_id=result.context.target.server_id,
        installation_id=result.context.target.installation_id,
        observed_at=observed,
        pano_version=__version__,
        sandbox=LocalSandbox(
            runtime=runtime_name,
            image=image_name,
            image_digest=image_digest,
            tracer=tracer,
        ),
        package_resolved=(package.resolved or package.pinned) if package is not None else None,
        protocol=ProtocolInfo(
            era=ProtocolEra(protocol.era.value),
            requested_version=protocol.requested_version,
            selected_version=protocol.selected_version,
            discovery_reason=(
                DiscoveryReason.MODERN_METADATA
                if protocol.era.value == "modern"
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
            for tool in result.tools
        ),
        spans=spans,
        declared=declaration.persisted,
        findings=(),
        state=state,
    )
    diagnostics = (
        *result.diagnostics,
        *(("UNATTRIBUTED_EVENTS",) if uncovered else ()),
        *(("NOISE_FILTERED_EVENTS:" + str(filtered_count),) if filtered_count else ()),
    )
    return WatchObservationBuild(
        observation,
        uncovered,
        diagnostics,
        declaration.scope,
        filtered_events=filtered_count,
    )


__all__ = ["WatchObservationBuild", "build_watch_observation"]
