"""Immutable typed inputs and matches for configuration analysis."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

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
    env_values: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    allowed_paths: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    filesystem_servers: frozenset[str] = frozenset()
    token_header_keys: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


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
