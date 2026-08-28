# Copyright (c) 2026 MCP Sentinel contributors
# SPDX-License-Identifier: MIT
"""Value-only semantic cache boundary adapted from pinned MCP-Sentinel logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ReviewCacheRecord:
    key: str
    response_json: str


class ReviewCache(Protocol):
    def get(self, key: str) -> ReviewCacheRecord | None: ...


class MemoryReviewCache:
    def __init__(self, records: tuple[ReviewCacheRecord, ...] = ()) -> None:
        self._records = {record.key: record for record in records}

    def get(self, key: str) -> ReviewCacheRecord | None:
        return self._records.get(key)
