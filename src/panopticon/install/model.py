"""Immutable install request, plan and outcome models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from panopticon.models import JsonPointer


class InstallAction(StrEnum):
    INSTALL = "install"
    UNINSTALL = "uninstall"


@dataclass(frozen=True, slots=True)
class InstallRequest:
    client: str
    action: InstallAction = InstallAction.INSTALL
    only: str | None = None
    dry_run: bool = False
    yes: bool = False
    pano_command: str = "pano"


@dataclass(frozen=True, slots=True)
class InstallPlan:
    config_path: Path
    pointer: JsonPointer
    patches: tuple[object, ...]
    server_name: str
    restart_hint: str | None = None
    reason_code: str = "INSTALL_PLANNED"


@dataclass(frozen=True, slots=True)
class InstallOutcome:
    server_name: str
    status: str
    reason_code: str
    plan: InstallPlan | None = None
    transaction_id: str | None = None


@dataclass(frozen=True, slots=True)
class InstallBatchOutcome:
    outcomes: tuple[InstallOutcome, ...]


__all__ = [
    "InstallAction",
    "InstallBatchOutcome",
    "InstallOutcome",
    "InstallPlan",
    "InstallRequest",
]
