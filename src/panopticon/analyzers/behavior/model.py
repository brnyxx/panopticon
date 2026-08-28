"""Typed, immutable inputs and outcomes for WATCH analysis."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from panopticon.models.ids import InstallationId, ObservationId, ServerId

from .spans import SpanKind


class EvidenceKind(StrEnum):
    FILE = "file"
    STAT = "stat"
    READ = "read"
    WRITE = "write"
    NETWORK = "network"
    DNS = "dns"
    CONNECT = "connect"
    REQUEST = "request"
    PROXY = "proxy"
    PROCESS = "process"
    STDERR = "stderr"
    URL = "url"
    LEAK = "leak"
    PLAINTEXT = "plaintext"


class CoverageState(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NONE = "NONE"
    UNSUPPORTED = "UNSUPPORTED"


class DeclaredAuthority(StrEnum):
    AUTHORITATIVE = "AUTHORITATIVE"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


class OutcomeState(StrEnum):
    MATCH = "MATCH"
    CLEAR = "CLEAR"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class WatchEvidence:
    kind: EvidenceKind
    value: str
    operation: str = ""
    span_id: str | None = None
    span_kind: SpanKind | None = None
    source: str = "trace"
    declared: bool = False
    certain: bool = True
    tls: bool = False
    post: bool = False

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("watch evidence value must be non-empty")


@dataclass(frozen=True, slots=True)
class Authority:
    """Per-tool declaration and source coverage, with no secret material."""

    tool: str
    paths: tuple[str, ...] = ()
    hosts: tuple[str, ...] = ()
    processes: tuple[str, ...] = ()
    read_only_hint: bool | None = None
    coverage: CoverageState = CoverageState.NONE
    authority: DeclaredAuthority = DeclaredAuthority.NONE


@dataclass(frozen=True, slots=True)
class BehaviorInput:
    evidence: tuple[WatchEvidence, ...] = ()
    authorities: tuple[Authority, ...] = ()
    decoys: frozenset[str] = frozenset()
    coverage: Mapping[EvidenceKind, CoverageState] = field(default_factory=dict)
    complete_spans: bool = True
    withheld: bool = False
    suppressed_rule_ids: frozenset[str] = frozenset()
    current_tool: str | None = None
    server_id: ServerId | None = None
    installation_id: InstallationId | None = None
    observation_id: ObservationId | None = None
    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        normalized = {
            EvidenceKind(key): CoverageState(value) for key, value in self.coverage.items()
        }
        object.__setattr__(self, "coverage", MappingProxyType(normalized))


@dataclass(frozen=True, slots=True)
class WatchMatch:
    rule_id: str
    state: OutcomeState
    evidence: tuple[WatchEvidence, ...] = ()
    excluded: tuple[WatchEvidence, ...] = ()
    reason: str = ""
    suppressed: bool = False


@dataclass(frozen=True, slots=True)
class WatchRule:
    rule_id: str
    severity: str
    kind: str
    condition: str


BehaviorEvidence = WatchEvidence
WatchContext = BehaviorInput

__all__ = [
    "Authority",
    "BehaviorEvidence",
    "BehaviorInput",
    "CoverageState",
    "DeclaredAuthority",
    "EvidenceKind",
    "OutcomeState",
    "WatchContext",
    "WatchEvidence",
    "WatchMatch",
    "WatchRule",
]
