"""Branded identifiers and canonical identity derivation."""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum, unique
from typing import Annotated, NewType

from pydantic import StringConstraints

from panopticon.models.common import ContractViolationError, NonEmptyStr, StrictModel

ServerId = NewType("ServerId", str)
InstallationId = NewType("InstallationId", str)
ObservationId = NewType("ObservationId", str)
BaselineId = NewType("BaselineId", str)
FindingId = NewType("FindingId", str)
LogicalKey = NewType("LogicalKey", str)
SpanId = NewType("SpanId", str)
ConfigPath = NewType("ConfigPath", str)
JsonPointer = NewType("JsonPointer", str)

ServerIdValue = Annotated[
    ServerId, StringConstraints(pattern=r"^(npm|pypi|github|docker|remote|local):.+$")
]
InstallationIdValue = Annotated[InstallationId, StringConstraints(pattern=r"^inst_[0-9a-f]{16}$")]
ObservationIdValue = Annotated[ObservationId, StringConstraints(pattern=r"^obs_[a-z0-9_-]+$")]
BaselineIdValue = Annotated[BaselineId, StringConstraints(pattern=r"^bl_[a-z0-9_-]+$")]
FindingIdValue = Annotated[FindingId, StringConstraints(pattern=r"^[0-9a-f]{16}$")]
LogicalKeyValue = Annotated[LogicalKey, StringConstraints(pattern=r"^lk_[0-9a-f]{16}$")]
SpanIdValue = Annotated[SpanId, StringConstraints(pattern=r"^.+:[0-9]+$")]
ConfigPathValue = Annotated[ConfigPath, StringConstraints(pattern=r"^~(?:/[^/]+)*$")]
JsonPointerValue = Annotated[JsonPointer, StringConstraints(pattern=r"^(?:/(?:[^~/]|~[01])*)+$")]


@unique
class ClientName(StrEnum):
    CLAUDE_DESKTOP = "claude-desktop"
    CLAUDE_CODE = "claude-code"
    CURSOR = "cursor"
    VSCODE = "vscode"
    WINDSURF = "windsurf"
    GENERIC = "generic"


@unique
class ConfigScope(StrEnum):
    GLOBAL = "global"
    PROJECT = "project"


class InstallationIdentityComponents(StrictModel):
    """Canonical per-entry components used to derive an installation identity."""

    client: ClientName
    config_path: ConfigPathValue
    scope: ConfigScope
    config_pointer: JsonPointerValue
    entry_name: NonEmptyStr


def _canonical_windows_path(value: str) -> tuple[str, bool]:
    slashed = re.sub(r"/+", "/", value.replace("\\", "/"))
    wsl = re.fullmatch(r"/mnt/([A-Za-z])(?:/(.*))?", slashed)
    if wsl is not None:
        suffix = wsl.group(2) or ""
        return f"{wsl.group(1).casefold()}:/{suffix}", True
    if re.match(r"^[A-Za-z]:/", slashed):
        return f"{slashed[0].casefold()}{slashed[1:]}", True
    if value.startswith(("\\\\", "//")):
        return f"//{slashed.lstrip('/')}", True
    return slashed, False


def _safe_relative(value: str, *, fold_case: bool) -> ConfigPath:
    relative = value.strip("/")
    segments = relative.split("/") if relative else []
    if any(segment in {"", ".", ".."} for segment in segments):
        raise ContractViolationError("INVALID_CONFIG_PATH", value)
    suffix = "/".join(segment.casefold() if fold_case else segment for segment in segments)
    return ConfigPath("~" if not suffix else f"~/{suffix}")


def normalize_config_path(path: str, home: str) -> ConfigPath:
    """Normalize supported native path forms without retaining the real home."""
    if path == "~" or path.startswith(("~/", "~\\")):
        return _safe_relative(path[2:] if path != "~" else "", fold_case=False)

    canonical_path, path_is_windows = _canonical_windows_path(path)
    canonical_home, home_is_windows = _canonical_windows_path(home)
    fold_case = path_is_windows or home_is_windows
    compared_path = canonical_path.casefold() if fold_case else canonical_path
    compared_home = (
        canonical_home.rstrip("/").casefold() if fold_case else canonical_home.rstrip("/")
    )
    if compared_path == compared_home:
        return ConfigPath("~")
    prefix = f"{compared_home}/"
    if not compared_path.startswith(prefix):
        raise ContractViolationError("CONFIG_PATH_OUTSIDE_HOME", path)
    relative = canonical_path[len(canonical_home.rstrip("/")) + 1 :]
    return _safe_relative(relative, fold_case=fold_case)


def _digest(parts: tuple[str, ...], prefix: str) -> str:
    canonical = json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
    return f"{prefix}{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


def derive_installation_id(components: InstallationIdentityComponents) -> InstallationId:
    """Derive the per-config-entry identity from canonical components."""
    return InstallationId(
        _digest(
            (
                components.client.value,
                components.config_path,
                components.scope.value,
                components.config_pointer,
                components.entry_name,
            ),
            "inst_",
        )
    )


def derive_logical_key(rule_id: str, installation_id: InstallationId, subject: str) -> LogicalKey:
    """Derive the stable finding join key independently of evidence."""
    return LogicalKey(_digest((rule_id, installation_id, subject), "lk_"))


def derive_span_id(tool: str, call_index: int) -> SpanId:
    """Address one deterministic tool-call span."""
    if not tool or call_index < 0:
        raise ContractViolationError("INVALID_SPAN_COMPONENT", f"{tool}:{call_index}")
    return SpanId(f"{tool}:{call_index}")
