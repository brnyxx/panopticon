"""Typed trace records and low-level strace parsing helpers."""

from __future__ import annotations

import ast
import posixpath
import re
from dataclasses import dataclass, field
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
    OVERFLOW = "OVERFLOW"
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
    child_pid: int | None = None
    confirmed: bool = True


@dataclass(frozen=True, slots=True)
class TraceResult:
    events: tuple[TraceEvent, ...]
    status: TraceStatus
    reason: TraceReason
    diagnostics: tuple[str, ...] = ()


@dataclass(slots=True)
class ProcessState:
    cwd: str = "/home/pano"
    fds: dict[int, str] = field(default_factory=dict)

    def clone(self) -> ProcessState:
        return ProcessState(self.cwd, dict(self.fds))


PREFIX: Final = re.compile(r"^(?:(?P<pid>\d+)\s+)?(?P<ts>\d+(?:\.\d+)?)\s+(?P<body>.*)$")
CALL: Final = re.compile(
    r"(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\((?P<args>.*)\)\s+=\s+"
    r"(?P<res>-?\d+|0x[0-9a-fA-F]+|[-A-Z]+)(?:\s+.*)?$"
)
OPERATIONS: Final = {
    "open": "open",
    "openat": "open",
    "stat": "stat",
    "newfstatat": "stat",
    "fstat": "stat",
    "readlink": "stat",
    "read": "read",
    "pread64": "read",
    "write": "write",
    "pwrite64": "write",
    "mmap": "mmap",
    "mmap2": "mmap",
    "execve": "exec",
    "execveat": "exec",
    "connect": "connect",
    "sendto": "send",
    "sendmsg": "send",
    "bind": "bind",
    "clone": "clone",
    "fork": "fork",
    "vfork": "fork",
    "chdir": "chdir",
    "fchdir": "chdir",
    "close": "close",
    "dup": "dup",
    "dup2": "dup",
    "dup3": "dup",
}
PATH_INDEX: Final = {
    "open": 0,
    "openat": 1,
    "stat": 0,
    "newfstatat": 1,
    "readlink": 0,
    "execve": 0,
    "execveat": 1,
    "chdir": 0,
}


def unquote(value: str) -> str | None:
    token = re.match(r'"(?:\\.|[^"\\])*"', value.strip())
    if token is None:
        return None
    try:
        decoded = ast.literal_eval(token.group(0))
    except (SyntaxError, ValueError):
        return None
    return decoded if isinstance(decoded, str) else None


def arguments(raw: str) -> tuple[str, ...]:
    out: list[str] = []
    start = depth = 0
    quoted = escaped = False
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
            if part := raw[start:index].strip():
                out.append(part)
            start = index + 1
    if part := raw[start:].strip():
        out.append(part)
    return tuple(out)


def integer(value: str) -> int | None:
    matched = re.match(r"-?(?:0x[0-9a-fA-F]+|\d+)", value.strip())
    if matched is None:
        return None
    try:
        return int(matched.group(0), 0)
    except ValueError:
        return None


def resolve_path(path: str, state: ProcessState, dirfd: str | None = None) -> str:
    if path.startswith("/"):
        return posixpath.normpath(path)
    base = state.cwd
    if dirfd and not dirfd.startswith("AT_FDCWD"):
        descriptor = integer(dirfd)
        if descriptor is not None:
            base = state.fds.get(descriptor, base)
    return posixpath.normpath(posixpath.join(base, path))
