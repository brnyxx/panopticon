"""Pure, fail-closed fix transaction state transitions."""

from __future__ import annotations

from dataclasses import replace

from .model import FixPlan, FixResult, FixState, digest
from .plan import apply_bytes, plan_hash


class FixConflictError(ValueError):
    """Current content or transaction state does not satisfy its precondition."""


def prepare(plan: FixPlan) -> FixResult:
    return FixResult(FixState.PLANNED, plan.target, plan.original_hash, plan_hash(plan))


def confirm(result: FixResult, approved: bool = True) -> FixResult:
    if result.state is not FixState.PLANNED:
        raise FixConflictError("INVALID_STATE")
    if not approved:
        return replace(result, reason="NOT_CONFIRMED")
    return replace(result, state=FixState.CONFIRMED)


def apply(plan: FixPlan, result: FixResult, current: bytes) -> FixResult:
    if result.state is not FixState.CONFIRMED:
        raise FixConflictError("INVALID_STATE")
    current_hash = digest(current)
    if current_hash != result.original_hash:
        return replace(
            result, state=FixState.CONFLICT, current_hash=current_hash, reason="SOURCE_STALE"
        )
    updated = apply_bytes(plan)
    return replace(
        result,
        state=FixState.APPLIED,
        apply_hash=digest(updated),
        current_hash=current_hash,
        bytes_value=updated,
    )


def recheck(result: FixResult, current: bytes, passed: bool) -> FixResult:
    if result.state is not FixState.APPLIED:
        raise FixConflictError("INVALID_STATE")
    current_hash = digest(current)
    if current_hash != result.apply_hash:
        return replace(
            result, state=FixState.CONFLICT, current_hash=current_hash, reason="USER_CHANGED"
        )
    return replace(result, state=FixState.RECHECKED, current_hash=current_hash)


def rollback(result: FixResult, current: bytes, original: bytes) -> FixResult:
    if result.state not in (FixState.APPLIED, FixState.RECHECKED):
        raise FixConflictError("INVALID_STATE")
    current_hash = digest(current)
    if current_hash != result.apply_hash:
        return replace(
            result, state=FixState.CONFLICT, current_hash=current_hash, reason="USER_CHANGED"
        )
    return replace(result, state=FixState.ROLLED_BACK, current_hash=current_hash, bytes_value=None)


def undo(result: FixResult, current: bytes, expected_current: str | None = None) -> FixResult:
    if result.state not in (FixState.RECHECKED, FixState.APPLIED):
        raise FixConflictError("INVALID_STATE")
    current_hash = digest(current)
    expected = expected_current or result.apply_hash
    if expected is None or current_hash != expected:
        return replace(
            result,
            state=FixState.CONFLICT,
            current_hash=current_hash,
            reason="UNDO_EXPECTATION_FAILED",
        )
    return replace(result, state=FixState.UNDONE, current_hash=current_hash, bytes_value=None)
