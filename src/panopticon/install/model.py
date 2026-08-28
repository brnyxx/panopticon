"""Immutable install request, transaction plan, and outcome contracts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from panopticon.fix.model import FixPlan
from panopticon.models.ids import JsonPointer
from panopticon.util.jsonc.patch import JsoncPatch


class InstallAction(StrEnum):
    INSTALL = "install"
    UNINSTALL = "uninstall"


class InstallStatus(StrEnum):
    PLANNED = "PLANNED"
    GUIDANCE = "GUIDANCE"
    RECHECKED = "RECHECKED"
    UNDONE = "UNDONE"
    ROLLED_BACK = "ROLLED_BACK"
    CONFLICT = "CONFLICT"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class InstallRequest:
    client: str
    action: InstallAction = InstallAction.INSTALL
    only: str | None = None
    config_path: Path | None = None
    dry_run: bool = True
    yes: bool = False
    pano_command: str | None = None


@dataclass(frozen=True, slots=True)
class InstallSelection:
    fix_id: str
    config_path: Path
    pointer: JsonPointer
    value: str | None = None
    transaction_pointer: JsonPointer | None = None

    def bind_transaction(self, plan: FixPlan, transaction_id: str) -> FixPlan:
        if self.transaction_pointer is None:
            return plan
        patches: list[JsoncPatch] = []
        for patch in plan.patches:
            if patch.pointer != self.transaction_pointer or not isinstance(patch.value, dict):
                patches.append(patch)
                continue
            metadata = dict(patch.value)
            metadata["transaction_id"] = transaction_id
            patches.append(replace(patch, value=metadata))
        return replace(plan, patches=tuple(patches))


@dataclass(frozen=True, slots=True)
class InstallPlan:
    fix_plan: FixPlan
    selection: InstallSelection
    server_name: str
    restart_hint_code: str
    reason_code: str

    @property
    def patches(self) -> tuple[JsoncPatch, ...]:
        return self.fix_plan.patches


@dataclass(frozen=True, slots=True)
class InstallOutcome:
    server_name: str
    status: InstallStatus
    reason_code: str
    plan: InstallPlan | None = None
    transaction_id: str | None = None


@dataclass(frozen=True, slots=True)
class InstallBatchOutcome:
    outcomes: tuple[InstallOutcome, ...]

    @property
    def successful(self) -> bool:
        return bool(self.outcomes) and all(
            outcome.status in {InstallStatus.PLANNED, InstallStatus.RECHECKED}
            or outcome.status is InstallStatus.UNDONE
            for outcome in self.outcomes
        )


__all__ = [
    "InstallAction",
    "InstallBatchOutcome",
    "InstallOutcome",
    "InstallPlan",
    "InstallRequest",
    "InstallSelection",
    "InstallStatus",
]
