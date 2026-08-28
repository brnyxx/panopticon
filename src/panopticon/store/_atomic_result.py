"""Typed outcomes shared by platform atomic replacement backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from panopticon.store.contracts import (
    AtomicConflict,
    AtomicOperation,
    DirectorySyncStatus,
    FailureCode,
    RejectionCode,
)


@dataclass(frozen=True, slots=True)
class AtomicSuccess:
    bytes_written: int
    directory_sync: DirectorySyncStatus


@dataclass(frozen=True, slots=True)
class AtomicRejected:
    code: RejectionCode


@dataclass(frozen=True, slots=True)
class AtomicFailure:
    code: FailureCode
    operation: AtomicOperation
    target_replaced: bool


AtomicResult: TypeAlias = AtomicSuccess | AtomicRejected | AtomicFailure | AtomicConflict


__all__ = ["AtomicFailure", "AtomicRejected", "AtomicResult", "AtomicSuccess"]
