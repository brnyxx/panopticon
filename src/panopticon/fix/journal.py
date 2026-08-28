"""Value-only append journal records for fix transactions."""

from __future__ import annotations

import json
from dataclasses import dataclass

from panopticon.models.common import NonEmptyStr, PersistedPathValue, StrictModel
from panopticon.models.ids import ConfigPath

from .model import FixResult, FixState, JournalEntry


class _JournalWire(StrictModel):
    transaction_id: NonEmptyStr
    target: PersistedPathValue
    state: FixState
    original_hash: NonEmptyStr
    plan_hash: NonEmptyStr
    apply_hash: str | None = None
    current_hash: str | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class JournalValue:
    entry: JournalEntry

    def as_bytes(self) -> bytes:
        return (
            json.dumps(
                self.entry.as_value(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")


def journal_entry(transaction_id: str, result: FixResult) -> JournalEntry:
    return JournalEntry(
        transaction_id,
        result.logical_target,
        result.state,
        result.original_hash,
        result.plan_hash,
        result.apply_hash,
        result.current_hash,
        result.reason,
    )


def append_value(transaction_id: str, result: FixResult) -> bytes:
    return JournalValue(journal_entry(transaction_id, result)).as_bytes()


def parse_value(data: bytes) -> tuple[JournalEntry, ...]:
    records: list[JournalEntry] = []
    for line in data.splitlines():
        if not line.strip():
            continue
        wire = _JournalWire.model_validate_json(line)
        records.append(
            JournalEntry(
                transaction_id=wire.transaction_id,
                target=ConfigPath(wire.target),
                state=wire.state,
                original_hash=wire.original_hash,
                plan_hash=wire.plan_hash,
                apply_hash=wire.apply_hash,
                current_hash=wire.current_hash,
                reason=wire.reason,
            )
        )
    return tuple(records)
