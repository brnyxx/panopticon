"""Deterministic parser for the pinned Linux strace entrypoint."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class TraceStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"


class TraceReason(StrEnum):
    COMPLETED = "COMPLETED"
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
    MALFORMED_LINE = "MALFORMED_LINE"
    TRUNCATED = "TRUNCATED"
    UNSUPPORTED_SYSCALL = "UNSUPPORTED_SYSCALL"


@dataclass(frozen=True, slots=True)
class TraceEvent:
    pid: int
    timestamp: float
    syscall: str
    operation: str
    arguments: tuple[str, ...]
    result: int | None
    path: str | None = None
    fd: int | None = None
    peer: str | None = None


@dataclass(frozen=True, slots=True)
class TraceResult:
    events: tuple[TraceEvent, ...]
    status: TraceStatus
    reason: TraceReason
    diagnostics: tuple[str, ...] = ()


_PREFIX: Final = re.compile(r"^(?:(?P<pid>\d+)\s+)?(?P<ts>\d+(?:\.\d+)?)\s+(?P<body>.*)$")
_CALL: Final = re.compile(
    r"(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\((?P<args>.*)\)\s+=\s+(?P<res>-?\d+|[-A-Z]+)(?:\s+.*)?$"
)
_SUPPORTED: Final = {
    "open": "read",
    "openat": "read",
    "stat": "stat",
    "newfstatat": "stat",
    "fstat": "stat",
    "readlink": "read",
    "execve": "exec",
    "execveat": "exec",
    "connect": "connect",
    "sendto": "send",
    "sendmsg": "send",
    "bind": "bind",
    "clone": "clone",
    "fork": "fork",
    "vfork": "fork",
}


def _unquote(value: str) -> str | None:
    value = value.strip()
    if not value.startswith('"'):
        return None
    try:
        token = re.match(r'"(?:\\.|[^"\\])*"', value)
        if token is None:
            return None
        decoded = ast.literal_eval(token.group(0))
    except (SyntaxError, ValueError):
        return None
    return decoded if isinstance(decoded, str) else None


def _args(raw: str) -> tuple[str, ...]:
    out: list[str] = []
    start = 0
    depth = 0
    quoted = False
    escaped = False
    for index, character in enumerate(raw):
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
            continue
        if character == '"':
            quoted = True
        elif character in "([{":
            depth += 1
        elif character in ")]}":
            depth = max(0, depth - 1)
        elif character == "," and depth == 0:
            part = raw[start:index].strip()
            if part:
                out.append(part)
            start = index + 1
    part = raw[start:].strip()
    if part:
        out.append(part)
    return tuple(out)


def _event(
    pid: int, ts: float, name: str, args: tuple[str, ...], result: int | None, tail: str
) -> TraceEvent:
    op = _SUPPORTED[name]
    if name in {"open", "openat"} and any(
        flag in args[-1] for flag in ("O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_APPEND")
    ):
        op = "write"
    path_indexes = {
        "open": 0,
        "openat": 1,
        "stat": 0,
        "newfstatat": 1,
        "readlink": 0,
        "execve": 0,
        "execveat": 1,
    }
    path_index = path_indexes.get(name)
    path = _unquote(args[path_index]) if path_index is not None and len(args) > path_index else None
    peer = tail.strip() or None
    if name in {"connect", "bind"} and len(args) > 1:
        peer = args[1]
    elif name in {"sendto", "sendmsg"} and args:
        peer = next((arg for arg in reversed(args) if "sin_" in arg or "sun_path" in arg), peer)
    fd = None
    if args:
        fd_match = re.search(r"\b(\d+)\b", args[0])
        if fd_match and name in {"connect", "bind", "sendto", "sendmsg", "readlink", "fstat"}:
            fd = int(fd_match.group(1))
    return TraceEvent(pid, ts, name, op, args, result, path, fd, peer)


def parse_strace(text: str) -> TraceResult:
    """Parse strace ``-f -ttt -yy`` output, retaining malformed coverage."""
    pending: dict[tuple[int, str], tuple[float, str]] = {}
    events: list[TraceEvent] = []
    diagnostics: list[str] = []
    unsupported = False
    malformed = False
    lines = text.splitlines()
    for line in lines:
        match = _PREFIX.match(line)
        if not match:
            if line.strip():
                malformed = True
                diagnostics.append(TraceReason.MALFORMED_LINE.value)
            continue
        pid = int(match.group("pid") or 0)
        ts = float(match.group("ts"))
        body = match.group("body")
        if body.endswith(" <unfinished ...>"):
            start = body.index("(")
            name = body[:start]
            pending[(pid, name)] = (ts, body.removesuffix(" <unfinished ...>"))
            continue
        resumed = re.match(r"<\.\.\.\s+(\w+) resumed>\s*(.*)$", body)
        if resumed:
            name, rest = resumed.groups()
            prior = pending.pop((pid, name), None)
            if prior is None:
                malformed = True
                diagnostics.append(TraceReason.MALFORMED_LINE.value)
                continue
            body = prior[1] + rest
            ts = prior[0]
        call = _CALL.match(body)
        if not call:
            malformed = True
            diagnostics.append(TraceReason.MALFORMED_LINE.value)
            continue
        name = call.group("name")
        if name not in _SUPPORTED:
            unsupported = True
            diagnostics.append(f"{TraceReason.UNSUPPORTED_SYSCALL.value}:{name}")
            continue
        raw_result = call.group("res")
        result = int(raw_result) if raw_result.lstrip("-").isdigit() else None
        events.append(
            _event(pid, ts, name, _args(call.group("args")), result, body[call.end("res") :])
        )
    if pending:
        diagnostics.append(TraceReason.TRUNCATED.value)
    status = (
        TraceStatus.FAILED
        if malformed and not events
        else TraceStatus.PARTIAL
        if (pending or malformed or unsupported)
        else TraceStatus.COMPLETE
    )
    reason = (
        TraceReason.TRUNCATED
        if pending
        else TraceReason.MALFORMED_LINE
        if malformed
        else TraceReason.UNSUPPORTED_SYSCALL
        if unsupported
        else TraceReason.COMPLETED
    )
    return TraceResult(tuple(events), status, reason, tuple(dict.fromkeys(diagnostics)))


parse = parse_strace
