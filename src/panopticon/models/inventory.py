"""Immutable installed-server persistence contract."""

from __future__ import annotations

from enum import StrEnum, unique
from typing import Self, assert_never

from pydantic import AnyHttpUrl, model_validator

from panopticon.models.common import ContractViolationError, NonEmptyStr, SchemaVersion, StrictModel
from panopticon.models.ids import (
    ClientName,
    ConfigPathValue,
    ConfigScope,
    InstallationIdValue,
    JsonPointerValue,
    ServerIdValue,
)


@unique
class Transport(StrEnum):
    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"


@unique
class PackageEcosystem(StrEnum):
    NPM = "npm"
    PYPI = "pypi"
    DOCKER = "docker"


@unique
class SourceKind(StrEnum):
    REGISTRY = "registry"
    GIT = "git"
    LOCAL = "local"
    REMOTE = "remote"


@unique
class IdentityConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PackageIdentity(StrictModel):
    ecosystem: PackageEcosystem
    name: NonEmptyStr
    pinned: NonEmptyStr | None
    resolved: NonEmptyStr | None


class InstallationSource(StrictModel):
    kind: SourceKind
    url: AnyHttpUrl | None


class InstalledServer(StrictModel):
    schema_version: SchemaVersion
    server_id: ServerIdValue
    installation_id: InstallationIdValue
    name: NonEmptyStr
    client: ClientName
    config_path: ConfigPathValue
    config_pointer: JsonPointerValue
    scope: ConfigScope
    transport: Transport
    command: NonEmptyStr | None
    args: tuple[str, ...]
    env_keys: tuple[NonEmptyStr, ...]
    url: AnyHttpUrl | None
    headers_keys: tuple[NonEmptyStr, ...]
    package: PackageIdentity | None
    source: InstallationSource
    identity_confidence: IdentityConfidence
    disabled: bool
    wrapped: bool

    @model_validator(mode="after")
    def enforce_transport_fields(self) -> Self:
        match self.transport:
            case Transport.STDIO:
                if self.command is None or self.url is not None:
                    raise ContractViolationError("INVALID_STDIO_FIELDS", self.name)
            case Transport.HTTP | Transport.SSE:
                if self.url is None or self.command is not None:
                    raise ContractViolationError("INVALID_REMOTE_FIELDS", self.name)
            case unreachable:
                assert_never(unreachable)
        return self
