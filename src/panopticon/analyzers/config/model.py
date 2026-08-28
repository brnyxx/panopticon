"""Immutable typed inputs and matches for configuration analysis."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from panopticon.models.ids import ObservationId
from panopticon.models.inventory import InstalledServer


class ConfigSeverity(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class ConfigKind(StrEnum):
    CONFIRMED = "confirmed"
    REVIEW = "review"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class ConfigEvidence:
    subject: str
    classification: str


@dataclass(frozen=True, slots=True)
class ConfigInput:
    """Normalized, secret-free facts paired with immutable inventory records."""

    servers: tuple[InstalledServer, ...] = ()
    env_values: Mapping[str, tuple[str, ...]] = field(default_factory=dict, repr=False)
    allowed_paths: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    filesystem_servers: frozenset[str] = frozenset()
    token_header_keys: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    observation_id: ObservationId | None = None
    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "env_values", MappingProxyType(dict(self.env_values)))
        object.__setattr__(self, "allowed_paths", MappingProxyType(dict(self.allowed_paths)))
        object.__setattr__(
            self,
            "token_header_keys",
            MappingProxyType(dict(self.token_header_keys)),
        )
        if self.observed_at is not None and (
            self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None
        ):
            raise ValueError("observed_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ConfigMatch:
    rule_id: str
    severity: ConfigSeverity
    kind: ConfigKind
    fix_id: str | None
    server_id: str
    installation_id: str
    evidence: tuple[ConfigEvidence, ...]


@dataclass(frozen=True, slots=True)
class ConfigRule:
    rule_id: str
    severity: ConfigSeverity
    kind: ConfigKind
    fix_id: str | None
    condition: str
