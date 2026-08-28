"""Deterministic stateful parser for the pinned Linux strace entrypoint."""

from __future__ import annotations

import re

from .trace_model import (
    CALL,
    OPERATIONS,
    PATH_INDEX,
    PREFIX,
    ProcessState,
    TraceAbsenceStatus,
    TraceEvent,
    TraceReason,
    TraceResult,
    TraceStatus,
    arguments,
    integer,
    resolve_path,
    unquote,
)


class TraceParser:
    def __init__(self, *, max_bytes: int = 8_388_608, max_events: int = 100_000) -> None:
        if max_bytes < 0 or max_events < 0:
            raise ValueError("trace bounds must be non-negative")
        self.max_bytes = max_bytes
        self.max_events = max_events
        self._states: dict[int, ProcessState] = {}
        self._pending: dict[tuple[int, str], tuple[float, str]] = {}
        self._events: list[TraceEvent] = []
        self._diagnostics: list[str] = []
        self._malformed = self._unsupported = self._overflow = False

    def _state(self, pid: int) -> ProcessState:
        return self._states.setdefault(pid, ProcessState())

    def _event(
        self,
        pid: int,
        timestamp: float,
        syscall: str,
        call_arguments: tuple[str, ...],
        result: int | None,
    ) -> TraceEvent:
        state = self._state(pid)
        operation = OPERATIONS[syscall]
        fd = integer(call_arguments[0]) if call_arguments else None
        path_index = PATH_INDEX.get(syscall)
        raw_path = (
            unquote(call_arguments[path_index])
            if path_index is not None and len(call_arguments) > path_index
            else None
        )
        dirfd = call_arguments[0] if syscall in {"openat", "newfstatat", "execveat"} else None
        path = resolve_path(raw_path, state, dirfd) if raw_path is not None else None
        if operation in {"read", "write", "mmap", "stat"} and path is None and fd is not None:
            path = state.fds.get(fd)
        if operation == "mmap" and len(call_arguments) > 4:
            fd = integer(call_arguments[4])
            path = state.fds.get(fd) if fd is not None and fd >= 0 else None
            operation = "read" if "PROT_READ" in call_arguments[2] else "mmap"
        peer = self._peer(syscall, call_arguments)
        child_pid = result if operation in {"clone", "fork"} and result and result > 0 else None
        confirmed = result is not None and result >= 0 and operation not in {"open", "stat"}
        event = TraceEvent(
            pid,
            timestamp,
            syscall,
            operation,
            call_arguments,
            result,
            path,
            fd,
            peer,
            child_pid,
            confirmed,
        )
        self._update_state(event, state)
        return event

    @staticmethod
    def _peer(syscall: str, call_arguments: tuple[str, ...]) -> str | None:
        if syscall in {"connect", "bind"} and len(call_arguments) > 1:
            return call_arguments[1]
        if syscall in {"sendto", "sendmsg"}:
            return next(
                (item for item in reversed(call_arguments) if "sin_" in item or "sun_path" in item),
                None,
            )
        return None

    def _update_state(self, event: TraceEvent, state: ProcessState) -> None:
        syscall = event.syscall
        result = event.result
        fd = event.fd
        if syscall in {"open", "openat"} and result is not None and result >= 0 and event.path:
            state.fds[result] = event.path
        elif event.operation in {"clone", "fork"} and event.child_pid is not None:
            self._states[event.child_pid] = state.clone()
        elif syscall == "chdir" and result == 0 and event.path:
            state.cwd = event.path
        elif syscall == "fchdir" and result == 0 and fd is not None and fd in state.fds:
            state.cwd = state.fds[fd]
        elif syscall == "close" and result == 0 and fd is not None:
            state.fds.pop(fd, None)
        elif event.operation == "dup" and result is not None and result >= 0 and fd in state.fds:
            state.fds[result] = state.fds[fd]

    def parse(self, text: str) -> TraceResult:
        encoded = text.encode()
        if len(encoded) > self.max_bytes:
            text = encoded[: self.max_bytes].decode(errors="ignore")
            self._overflow = True
            self._diagnostics.append(TraceReason.OVERFLOW.value)
        for line in text.splitlines():
            self._parse_line(line)
            if len(self._events) >= self.max_events:
                self._overflow = True
                self._diagnostics.append(TraceReason.OVERFLOW.value)
                break
        return self._result()

    def _parse_line(self, line: str) -> None:
        matched = PREFIX.match(line)
        if matched is None:
            if line.strip():
                self._malformed = True
                self._diagnostics.append(TraceReason.MALFORMED_LINE.value)
            return
        pid = int(matched.group("pid") or 0)
        timestamp = float(matched.group("ts"))
        body = matched.group("body")
        if body.endswith(" <unfinished ...>"):
            name = body.split("(", 1)[0]
            self._pending[(pid, name)] = (timestamp, body.removesuffix(" <unfinished ...>"))
            return
        if resumed := re.match(r"<\.\.\.\s+(\w+) resumed>\s*(.*)$", body):
            name, rest = resumed.groups()
            prior = self._pending.pop((pid, name), None)
            if prior is None:
                self._malformed = True
                self._diagnostics.append(TraceReason.MALFORMED_LINE.value)
                return
            timestamp, body = prior[0], prior[1] + rest
        call = CALL.match(body)
        if call is None:
            self._malformed = True
            self._diagnostics.append(TraceReason.MALFORMED_LINE.value)
            return
        syscall = call.group("name")
        if syscall not in OPERATIONS:
            self._unsupported = True
            self._diagnostics.append(f"{TraceReason.UNSUPPORTED_SYSCALL.value}:{syscall}")
            return
        self._events.append(
            self._event(
                pid,
                timestamp,
                syscall,
                arguments(call.group("args")),
                integer(call.group("res")),
            )
        )

    def _result(self) -> TraceResult:
        if self._pending:
            self._diagnostics.append(TraceReason.TRUNCATED.value)
        has_issue = bool(self._pending) or self._malformed or self._unsupported or self._overflow
        status = (
            TraceStatus.FAILED
            if self._malformed and not self._events
            else TraceStatus.PARTIAL
            if has_issue
            else TraceStatus.COMPLETE
        )
        reason = (
            TraceReason.OVERFLOW
            if self._overflow
            else TraceReason.TRUNCATED
            if self._pending
            else TraceReason.MALFORMED_LINE
            if self._malformed
            else TraceReason.UNSUPPORTED_SYSCALL
            if self._unsupported
            else TraceReason.COMPLETED
        )
        return TraceResult(
            tuple(self._events),
            status,
            reason,
            tuple(dict.fromkeys(self._diagnostics)),
        )


def parse_strace(
    text: str,
    *,
    max_bytes: int = 8_388_608,
    max_events: int = 100_000,
) -> TraceResult:
    return TraceParser(max_bytes=max_bytes, max_events=max_events).parse(text)


parse = parse_strace

__all__ = [
    "TraceAbsenceStatus",
    "TraceEvent",
    "TraceParser",
    "TraceReason",
    "TraceResult",
    "TraceStatus",
    "parse",
    "parse_strace",
]
