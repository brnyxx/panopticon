"""Immutable local and remote observation persistence contracts."""

from __future__ import annotations

from enum import StrEnum, unique
from typing import Annotated, Literal, Self, TypeAlias, assert_never

from pydantic import AnyHttpUrl, Field, model_validator

from panopticon.models.common import (
    ContractViolationError,
    HostValue,
    NonEmptyStr,
    PersistedPathValue,
    SchemaVersion,
    StrictModel,
    UtcDateTime,
)
from panopticon.models.event import Event
from panopticon.models.finding import Finding
from panopticon.models.ids import (
    InstallationIdValue,
    ObservationIdValue,
    ServerIdValue,
    SpanIdValue,
)
from panopticon.models.state import ObservationState, ReasonCode, StageStatus


@unique
class ProtocolEra(StrEnum):
    MODERN = "modern"
    LEGACY = "legacy"


@unique
class DiscoveryReason(StrEnum):
    MODERN_METADATA = "MODERN_METADATA"
    SERVER_DISCOVERY = "SERVER_DISCOVERY"
    LEGACY_HANDSHAKE = "LEGACY_HANDSHAKE"


@unique
class FallbackReason(StrEnum):
    NONE = "NONE"
    VERSION_RETRY = "VERSION_RETRY"
    LEGACY_REQUIRED = "LEGACY_REQUIRED"
    STREAMABLE_HTTP_UNAVAILABLE = "STREAMABLE_HTTP_UNAVAILABLE"
    DEPRECATED_SSE = "DEPRECATED_SSE"


class ServerInfo(StrictModel):
    name: NonEmptyStr
    version: NonEmptyStr


class ProtocolInfo(StrictModel):
    era: ProtocolEra
    requested_version: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    selected_version: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    discovery_reason: DiscoveryReason
    fallback_reason: FallbackReason
    server_info: ServerInfo
    capabilities: tuple[NonEmptyStr, ...]


class LocalSandbox(StrictModel):
    runtime: Literal["docker", "podman"]
    image: NonEmptyStr
    image_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    tracer: NonEmptyStr


class RemoteSandbox(StrictModel):
    runtime: Literal["remote"]
    transport: Literal["streamable_http", "sse"]
    endpoint: AnyHttpUrl


Sandbox: TypeAlias = Annotated[LocalSandbox | RemoteSandbox, Field(discriminator="runtime")]


class ToolAnnotations(StrictModel):
    read_only: bool
    destructive: bool
    open_world: bool


class ToolInfo(StrictModel):
    name: NonEmptyStr
    input_schema_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
    annotations: ToolAnnotations


@unique
class SpanResult(StrEnum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class Span(StrictModel):
    span_id: SpanIdValue
    tool: NonEmptyStr
    call_index: Annotated[int, Field(ge=0)]
    args_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
    result: SpanResult
    duration_ms: Annotated[int, Field(ge=0)]
    events: tuple[Event, ...]


@unique
class DeclaredCapability(StrEnum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    OPEN_WORLD = "open_world"


@unique
class DeclaredSource(StrEnum):
    SELF_DECL = "self_decl"
    REGISTRY = "registry"
    TOOL_DESCRIPTION = "tool_description"
    README = "readme"
    MANIFEST = "manifest"
    CONFIG = "config"


@unique
class DeclaredCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


class Declared(StrictModel):
    hosts: tuple[HostValue, ...]
    paths: tuple[PersistedPathValue, ...]
    env: tuple[NonEmptyStr, ...]
    processes: tuple[NonEmptyStr, ...]
    capabilities: tuple[DeclaredCapability, ...]
    sources: tuple[DeclaredSource, ...]
    completeness: DeclaredCompleteness


class Observation(StrictModel):
    schema_version: SchemaVersion
    observation_id: ObservationIdValue
    server_id: ServerIdValue
    installation_id: InstallationIdValue
    observed_at: UtcDateTime
    pano_version: NonEmptyStr
    sandbox: Sandbox
    package_resolved: NonEmptyStr | None
    protocol: ProtocolInfo
    tools: tuple[ToolInfo, ...]
    spans: tuple[Span, ...]
    declared: Declared
    findings: tuple[Finding, ...]
    state: ObservationState

    @model_validator(mode="after")
    def enforce_protocol_era_stages(self) -> Self:
        handshake = self.state.stages.handshake
        discovery = self.state.stages.version_discovery
        match self.protocol.era:
            case ProtocolEra.MODERN:
                valid_handshake = (
                    handshake.status is StageStatus.NOT_REQUESTED
                    and handshake.reason_code is ReasonCode.MODERN_HANDSHAKE_NOT_REQUESTED
                )
                valid_discovery = discovery.status is StageStatus.COMPLETE
                valid_fallback = self.protocol.fallback_reason in {
                    FallbackReason.NONE,
                    FallbackReason.VERSION_RETRY,
                }
            case ProtocolEra.LEGACY:
                valid_handshake = handshake.status is StageStatus.COMPLETE
                valid_discovery = (
                    discovery.status is StageStatus.PARTIAL
                    and discovery.reason_code is ReasonCode.LEGACY_FALLBACK
                )
                valid_fallback = self.protocol.fallback_reason is not FallbackReason.NONE
            case unreachable:
                assert_never(unreachable)
        if not (valid_handshake and valid_discovery and valid_fallback):
            raise ContractViolationError("INVALID_PROTOCOL_STAGE_TRANSITION", self.protocol.era)
        return self
