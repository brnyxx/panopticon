"""Closed persisted event variants."""

from __future__ import annotations

from typing import Annotated, Literal, Self, TypeAlias

from pydantic import ConfigDict, Field, RootModel, model_validator

from panopticon.models.common import (
    ContractViolationError,
    HostValue,
    NonEmptyStr,
    PersistedPathValue,
    SchemaVersion,
    StrictModel,
)


class FileEvent(StrictModel):
    schema_version: SchemaVersion
    kind: Literal["file"]
    op: Literal["read", "write", "stat", "exec", "create", "delete"]
    path: PersistedPathValue
    decoy: bool
    decoy_key: NonEmptyStr | None
    count: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def require_decoy_key(self) -> Self:
        if self.decoy and self.decoy_key is None:
            raise ContractViolationError("MISSING_DECOY_KEY", self.path)
        return self


class NetEvent(StrictModel):
    schema_version: SchemaVersion
    kind: Literal["net"]
    op: Literal["connect", "dns"]
    host: HostValue
    port: Annotated[int, Field(ge=1, le=65535)] | None
    via: Literal["proxy", "direct", "dns"]
    count: Annotated[int, Field(ge=1)]


class ProcessEvent(StrictModel):
    schema_version: SchemaVersion
    kind: Literal["proc"]
    op: Literal["exec"]
    argv: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    count: Annotated[int, Field(ge=1)]


class LeakEvent(StrictModel):
    schema_version: SchemaVersion
    kind: Literal["leak"]
    op: Literal["expose"]
    decoy_key: NonEmptyStr
    sink: NonEmptyStr
    count: Annotated[int, Field(ge=1)]


class BlockedEvent(StrictModel):
    schema_version: SchemaVersion
    kind: Literal["blocked"]
    op: Literal["connect"]
    host: HostValue
    port: Annotated[int, Field(ge=1, le=65535)]
    count: Annotated[int, Field(ge=1)]


class PlaintextHttpEvent(StrictModel):
    schema_version: SchemaVersion
    kind: Literal["plaintext_http"]
    op: Literal["request"]
    host: HostValue
    request_path: Annotated[str, Field(pattern=r"^/")]
    decoy_keys: tuple[NonEmptyStr, ...]
    count: Annotated[int, Field(ge=1)]


EventValue: TypeAlias = Annotated[
    FileEvent | NetEvent | ProcessEvent | LeakEvent | BlockedEvent | PlaintextHttpEvent,
    Field(discriminator="kind"),
]


class Event(RootModel[EventValue]):
    """Persistence-boundary root for the exhaustive event union."""

    model_config = ConfigDict(frozen=True, strict=True)
