"""Immutable value objects for transactional fixes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path

from panopticon.models.ids import ConfigPath
from panopticon.util.jsonc.patch import JsoncPatch


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@unique
class FixState(StrEnum):
    PLANNED = "PLANNED"
    CONFIRMED = "CONFIRMED"
    APPLIED = "APPLIED"
    RECHECKED = "RECHECKED"
    ROLLED_BACK = "ROLLED_BACK"
    UNDONE = "UNDONE"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class FixPrompt:
    name: str
    description: str = ""
    required: bool = True

    def __repr__(self) -> str:
        return (
            f"FixPrompt(name={self.name!r}, description={self.description!r}, "
            f"required={self.required!r})"
        )


@dataclass(frozen=True, slots=True)
class FixPlan:
    target: Path
    logical_target: ConfigPath
    original: bytes
    patches: tuple[JsoncPatch, ...] = ()
    prompts: tuple[FixPrompt, ...] = ()
    mode: int | None = None
    source_identity: tuple[int, int] | None = None

    @property
    def original_hash(self) -> str:
        return digest(self.original)

    def __repr__(self) -> str:
        return (
            f"FixPlan(target={str(self.target)!r}, "
            f"logical_target={str(self.logical_target)!r}, "
            f"original_hash={self.original_hash!r}, "
            f"patches={len(self.patches)}, prompts={len(self.prompts)})"
        )


@dataclass(frozen=True, slots=True)
class FixResult:
    state: FixState
    target: Path
    logical_target: ConfigPath
    original_hash: str
    plan_hash: str
    apply_hash: str | None = None
    current_hash: str | None = None
    reason: str = ""
    bytes_value: bytes | None = None

    def __repr__(self) -> str:
        return (
            f"FixResult(state={self.state.value!r}, target={str(self.target)!r}, "
            f"logical_target={str(self.logical_target)!r}, "
            f"original_hash={self.original_hash!r}, plan_hash={self.plan_hash!r}, "
            f"apply_hash={self.apply_hash!r}, current_hash={self.current_hash!r}, "
            f"reason={self.reason!r})"
        )


@dataclass(frozen=True, slots=True)
class BackupRequest:
    target: Path
    logical_target: ConfigPath
    plaintext: bytes
    source: str
    config_digest: str
    key_name: str = "panopticon/fix-backup"

    def __repr__(self) -> str:
        return "BackupRequest(<redacted>)"


@dataclass(frozen=True, slots=True)
class JournalEntry:
    transaction_id: str
    target: ConfigPath
    state: FixState
    original_hash: str
    plan_hash: str
    apply_hash: str | None = None
    current_hash: str | None = None
    reason: str = ""

    def as_value(self) -> dict[str, str | None]:
        return {
            "transaction_id": self.transaction_id,
            "target": str(self.target),
            "state": self.state.value,
            "original_hash": self.original_hash,
            "plan_hash": self.plan_hash,
            "apply_hash": self.apply_hash,
            "current_hash": self.current_hash,
            "reason": self.reason,
        }
