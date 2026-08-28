"""Immutable models for declared MCP scope."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType


class Authority(StrEnum):
    AUTHORITATIVE = "authoritative"
    PARTIAL = "partial"
    NONE = "none"


class Completeness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


class ScopeStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"
    INVALID = "INVALID"


class ScopeReason(StrEnum):
    DECLARED = "DECLARED"
    INFERRED = "INFERRED"
    MISSING = "MISSING"
    MALFORMED = "MALFORMED"
    CONFLICT = "CONFLICT"


class Capability(StrEnum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    OPEN_WORLD = "open_world"


class SourceKind(StrEnum):
    TOOL_DESCRIPTION = "tool_description"
    README = "readme"
    MANIFEST = "manifest"
    CONFIG = "config"
    REGISTRY = "registry"
    SELF_DECL = "self_decl"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str
    source: SourceKind | None = None


@dataclass(frozen=True, slots=True)
class Coverage:
    paths: ScopeStatus = ScopeStatus.UNKNOWN
    hosts: ScopeStatus = ScopeStatus.UNKNOWN
    env: ScopeStatus = ScopeStatus.UNKNOWN
    processes: ScopeStatus = ScopeStatus.UNKNOWN


@dataclass(frozen=True, slots=True)
class ScopeGrant:
    paths: tuple[str, ...] = ()
    hosts: tuple[str, ...] = ()
    ports: tuple[int, ...] = ()
    env: tuple[str, ...] = ()
    processes: tuple[str, ...] = ()
    capabilities: tuple[Capability, ...] = ()
    source: SourceKind = SourceKind.TOOL_DESCRIPTION
    confidence: float = 1.0
    authority: Authority = Authority.NONE
    maintainer: bool = False
    complete: bool = False
    diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between zero and one")
        if self.complete and self.authority is not Authority.AUTHORITATIVE:
            raise ValueError("complete scope must be authoritative")


@dataclass(frozen=True, slots=True)
class DeclaredScope:
    server: ScopeGrant = field(default_factory=ScopeGrant)
    tools: Mapping[str, ScopeGrant] = field(default_factory=dict)
    diagnostics: tuple[Diagnostic, ...] = ()
    coverage: Coverage = field(default_factory=Coverage)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tools", MappingProxyType(dict(self.tools)))

    @property
    def completeness(self) -> Completeness:
        grants = (self.server, *self.tools.values())
        if any(g.authority is Authority.AUTHORITATIVE and g.complete for g in grants):
            return Completeness.COMPLETE
        if any(
            g.authority is Authority.PARTIAL or g.paths or g.hosts or g.env or g.processes
            for g in grants
        ):
            return Completeness.PARTIAL
        return Completeness.NONE


@dataclass(frozen=True, slots=True)
class Match:
    status: ScopeStatus
    reason: ScopeReason
    field: str
    value: str
    source: SourceKind | None = None
