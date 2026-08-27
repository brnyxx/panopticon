"""Shared strict persistence-boundary primitives."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Literal, NewType

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints, WithJsonSchema

SchemaVersion = Literal["0.1"]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
PersistedPath = NewType("PersistedPath", str)
Host = NewType("Host", str)


@dataclass(frozen=True, slots=True)
class ContractViolationError(ValueError):
    """A machine-consumed persistence contract was violated."""

    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


def _validate_persisted_path(value: str) -> PersistedPath:
    normalized = value.replace("\\", "/")
    lowered = normalized.casefold()
    forbidden_prefixes = ("/users/", "/home/")
    has_drive_prefix = re.match(r"^[A-Za-z]:", normalized) is not None
    has_network_root = normalized.startswith("//")
    has_wsl_home = re.match(r"^/mnt/[a-z]/users/", lowered) is not None
    if (
        normalized != value
        or has_drive_prefix
        or has_network_root
        or has_wsl_home
        or any(lowered.startswith(prefix) for prefix in forbidden_prefixes)
    ):
        raise ContractViolationError("REAL_HOME_PATH", value)
    if "/../" in f"/{value}/" or value.endswith("/.."):
        raise ContractViolationError("PATH_TRAVERSAL", value)
    return PersistedPath(value)


def _validate_host(value: str) -> Host:
    if value != value.casefold():
        raise ContractViolationError("HOST_NOT_NORMALIZED", value)
    return Host(value)


def _validate_utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ContractViolationError("TIMESTAMP_NOT_UTC", value.isoformat())
    return value


PersistedPathValue = Annotated[
    PersistedPath,
    AfterValidator(_validate_persisted_path),
    WithJsonSchema(
        {
            "type": "string",
            "pattern": (
                r"^(?!.*\\)(?!\.\.(?:/|$))(?!.*\/\.\.(?:/|$))"
                r"(?!//)(?![A-Za-z]:)"
                r"(?!/[Uu][Ss][Ee][Rr][Ss]/)(?!/[Hh][Oo][Mm][Ee]/)"
                r"(?!/[Mm][Nn][Tt]/[A-Za-z]/[Uu][Ss][Ee][Rr][Ss]/).+"
            ),
        }
    ),
]
HostValue = Annotated[
    Host,
    AfterValidator(_validate_host),
    WithJsonSchema(
        {
            "type": "string",
            "format": "hostname",
            "pattern": r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$",
        }
    ),
]
UtcDateTime = Annotated[datetime, AfterValidator(_validate_utc)]


class StrictModel(BaseModel):
    """Immutable, closed Pydantic model used at persistence boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)
