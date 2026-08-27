"""Leak-aware structlog boundary with a closed engine event set."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique

import structlog

from panopticon.util.leak_check import LeakContext, find_leaks


@unique
class LogEvent(StrEnum):
    COMPLETE = "engine.complete"
    PARTIAL = "engine.partial"
    INCOMPLETE = "engine.incomplete"
    FAILED = "engine.failed"
    UNSUPPORTED = "engine.unsupported"


_EVENT_VALUES = frozenset(
    (
        LogEvent.COMPLETE.value,
        LogEvent.PARTIAL.value,
        LogEvent.INCOMPLETE.value,
        LogEvent.FAILED.value,
        LogEvent.UNSUPPORTED.value,
    )
)


@dataclass(frozen=True, slots=True)
class LogRecord:
    """Typed input whose detail and exception are inspection-only values."""

    event: str
    classification: str
    code: str
    detail: str
    exception: BaseException | None = None

    def __post_init__(self) -> None:
        if self.event not in _EVENT_VALUES:
            raise ValueError("unknown engine log event")
        if not self.classification or not self.classification.isupper():
            raise ValueError("log classification must be uppercase")
        if not self.code or not self.code.isupper():
            raise ValueError("log code must be uppercase")


def emit(record: LogRecord, context: LeakContext) -> None:
    """Inspect sensitive values and emit only stable machine fields."""
    exception_text = "" if record.exception is None else repr(record.exception)
    leak_views = (
        find_leaks(f"{record.detail}\n{exception_text}", context),
        find_leaks(
            f"{record.event}\n{record.classification}\n{record.code}",
            context,
        ),
    )
    if leak_views[1]:
        structlog.get_logger("panopticon").info(
            LogEvent.FAILED.value,
            classification="FAILED",
            code="LEAK_REDACTED",
        )
        return
    event = LogEvent(record.event)
    structlog.get_logger("panopticon").info(
        event.value,
        classification=record.classification,
        code=record.code,
    )


__all__ = ["LogEvent", "LogRecord", "emit"]
