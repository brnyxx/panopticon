"""Value-only append journal records for fix transactions."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .model import FixResult, FixState, JournalEntry


@dataclass(frozen=True, slots=True)
class JournalValue:
    entry: JournalEntry

    def as_bytes(self) -> bytes:
        return (
            json.dumps(
                self.entry.as_value(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            + "\n"
        ).encode("utf-8")


def journal_entry(transaction_id: str, result: FixResult) -> JournalEntry:
    return JournalEntry(
        transaction_id,
        result.target,
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
    records = []
    for line in data.splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        records.append(
            JournalEntry(
                transaction_id=str(value["transaction_id"]),
                target=__import__("pathlib").Path(value["target"]),
                state=FixState(value["state"]),
                original_hash=str(value["original_hash"]),
                plan_hash=str(value["plan_hash"]),
                apply_hash=value.get("apply_hash"),
                current_hash=value.get("current_hash"),
                reason=str(value.get("reason", "")),
            )
        )
    return tuple(records)
