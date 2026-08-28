"""Typed boundaries for the stdio wrapper core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from panopticon.models.event import Event


class Coverage(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"


class AsyncReader(Protocol):
    async def read(self, size: int = ...) -> bytes: ...


class AsyncWriter(Protocol):
    def write(self, data: bytes) -> None: ...
    async def drain(self) -> None: ...
    def close(self) -> None: ...
    async def wait_closed(self) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class Recorder(Protocol):
    def record(self, record: WrapRecordCandidate) -> None: ...


class Notifier(Protocol):
    def notify(self, alert: AlertCandidate) -> None: ...


@dataclass(frozen=True, slots=True)
class ToolSpan:
    tool: str
    request_id: str
    started_at: datetime
    finished_at: datetime

    @property
    def duration_ms(self) -> int:
        return max(0, int((self.finished_at - self.started_at).total_seconds() * 1000))


@dataclass(frozen=True, slots=True)
class WrapRecordCandidate:
    server_id: str
    installation_id: str
    span: ToolSpan
    events: tuple[Event, ...] = ()
    coverage: Coverage = Coverage.COMPLETE


@dataclass(frozen=True, slots=True)
class AlertCandidate:
    installation_id: str
    host: str
    process: str
    first_seen_at: datetime


@dataclass(frozen=True, slots=True)
class RelayResult:
    coverage: Coverage
    bytes_client_to_child: int
    bytes_child_to_client: int
    exit_code: int | None
    parser_errors: int = 0
    recorder_errors: int = 0
