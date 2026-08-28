"""Typed, prompt-free models for fix selection and outcomes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from panopticon.models.ids import JsonPointer
from panopticon.util.jsonc.patch import JsoncPatch

from .model import FixPlan


class FixChoice(StrEnum):
    APPLY = "APPLY"
    GUIDANCE = "GUIDANCE"
    DECLINE = "DECLINE"


class FixOutcomeStatus(StrEnum):
    PLANNED = "PLANNED"
    GUIDANCE = "GUIDANCE"
    DECLINED = "DECLINED"
    APPLIED = "APPLIED"
    RECHECKED = "RECHECKED"
    ROLLED_BACK = "ROLLED_BACK"
    UNDONE = "UNDONE"
    CONFLICT = "CONFLICT"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class FixSelection:
    fix_id: str
    config_path: Path
    pointer: JsonPointer
    choice: FixChoice = FixChoice.APPLY
    value: str | None = None
    version: str | None = None
    client: str | None = None

    def __post_init__(self) -> None:
        if re.fullmatch(r"FIX-(001|002|004|005|008|010)", self.fix_id) is None:
            raise ValueError("UNKNOWN_FIX_ID")

    def bind_transaction(self, plan: FixPlan, transaction_id: str) -> FixPlan:
        return plan


@dataclass(frozen=True, slots=True)
class FixRequest:
    selections: tuple[FixSelection, ...]
    dry_run: bool = True
    recheck: bool = True
    undo: bool = False


@dataclass(frozen=True, slots=True)
class FixOutcome:
    fix_id: str
    status: FixOutcomeStatus
    reason_code: str
    patches: tuple[JsoncPatch, ...] = ()
    written_paths: tuple[Path, ...] = ()
    transaction_id: str | None = None


@dataclass(frozen=True, slots=True)
class FixBatchOutcome:
    outcomes: tuple[FixOutcome, ...]

    @property
    def writes(self) -> int:
        return sum(len(outcome.written_paths) for outcome in self.outcomes)

    @property
    def guidance_only(self) -> bool:
        return bool(self.outcomes) and all(
            outcome.status in {FixOutcomeStatus.GUIDANCE, FixOutcomeStatus.DECLINED}
            for outcome in self.outcomes
        )


__all__ = [
    "FixBatchOutcome",
    "FixChoice",
    "FixOutcome",
    "FixOutcomeStatus",
    "FixRequest",
    "FixSelection",
]
