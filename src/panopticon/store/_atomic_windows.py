"""Windows path-based atomic replacement with reparse-point rejection."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from panopticon.store.contracts import (
    AtomicConflict,
    AtomicConflictReason,
    AtomicOperation,
    AtomicPrecondition,
    FailureCode,
    FaultInjector,
    RejectionCode,
)


@dataclass(frozen=True, slots=True)
class WindowsSuccess:
    bytes_written: int


@dataclass(frozen=True, slots=True)
class WindowsRejected:
    code: RejectionCode


@dataclass(frozen=True, slots=True)
class WindowsFailure:
    code: FailureCode
    operation: AtomicOperation
    target_replaced: bool


WindowsResult = WindowsSuccess | WindowsRejected | WindowsFailure | AtomicConflict


def _same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(os.fspath(first)) == os.path.normcase(os.fspath(second))


def _parent(target: Path, injector: FaultInjector) -> Path | WindowsRejected:
    injector.before(AtomicOperation.OPEN_PARENT)
    absolute = target.absolute()
    try:
        resolved = absolute.parent.resolve(strict=True)
    except OSError:
        return WindowsRejected(RejectionCode.UNSAFE_PARENT)
    if not _same_path(absolute.parent, resolved):
        return WindowsRejected(RejectionCode.UNSAFE_PARENT)
    return resolved


def _identity(target: Path) -> tuple[int, int] | WindowsRejected | None:
    try:
        metadata = target.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(metadata.st_mode):
        return WindowsRejected(RejectionCode.SYMLINK_TARGET)
    if not stat.S_ISREG(metadata.st_mode):
        return WindowsRejected(RejectionCode.UNSAFE_TARGET)
    return metadata.st_dev, metadata.st_ino


def _precondition(target: Path, expected: AtomicPrecondition) -> WindowsResult | None:
    identity = _identity(target)
    if isinstance(identity, WindowsRejected):
        return identity
    if identity != expected.identity:
        return AtomicConflict(AtomicConflictReason.IDENTITY_CHANGED, AtomicOperation.REPLACE)
    try:
        with target.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != expected.identity:
                return AtomicConflict(
                    AtomicConflictReason.IDENTITY_CHANGED,
                    AtomicOperation.REPLACE,
                )
            digest = hashlib.sha256(stream.read()).hexdigest()
    except FileNotFoundError:
        return AtomicConflict(AtomicConflictReason.IDENTITY_CHANGED, AtomicOperation.REPLACE)
    if digest != expected.sha256:
        return AtomicConflict(AtomicConflictReason.CONTENT_CHANGED, AtomicOperation.REPLACE)
    return None


def _cleanup(path: Path | None, injector: FaultInjector) -> WindowsFailure | None:
    if path is None:
        return None
    injected: WindowsFailure | None = None
    try:
        injector.before(AtomicOperation.CLEANUP)
    except PermissionError:
        injected = WindowsFailure(FailureCode.PERMISSION_DENIED, AtomicOperation.CLEANUP, False)
    except OSError:
        injected = WindowsFailure(FailureCode.CLEANUP_ERROR, AtomicOperation.CLEANUP, False)
    try:
        path.unlink()
    except FileNotFoundError:
        return injected
    except PermissionError:
        return WindowsFailure(FailureCode.PERMISSION_DENIED, AtomicOperation.CLEANUP, False)
    except OSError:
        return WindowsFailure(FailureCode.CLEANUP_ERROR, AtomicOperation.CLEANUP, False)
    return injected


def atomic_replace_windows(
    target: Path,
    data: bytes,
    injector: FaultInjector,
    *,
    expected_target: AtomicPrecondition | None,
    mode: int,
) -> WindowsResult:
    operation = AtomicOperation.OPEN_PARENT
    target_replaced = False
    temporary: Path | None = None
    result: WindowsResult
    try:
        parent = _parent(target, injector)
        if isinstance(parent, WindowsRejected):
            return parent
        absolute = parent / target.name
        initial = _identity(absolute)
        if isinstance(initial, WindowsRejected):
            return initial
        operation = AtomicOperation.CREATE_TEMP
        injector.before(operation)
        temporary = parent / f".{target.name}.{os.urandom(8).hex()}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        descriptor = os.open(temporary, flags, 0o600)
        try:
            temporary.chmod(mode)
            operation = AtomicOperation.WRITE
            injector.before(operation)
            offset = 0
            while offset < len(data):
                try:
                    written = os.write(descriptor, data[offset:])
                except InterruptedError:
                    continue
                if written <= 0:
                    raise OSError("descriptor write made no progress")
                offset += written
            operation = AtomicOperation.FLUSH
            injector.before(operation)
            operation = AtomicOperation.FILE_FSYNC
            injector.before(operation)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        operation = AtomicOperation.REPLACE
        injector.before(operation)
        if expected_target is None:
            current = _identity(absolute)
            conflict: WindowsResult | None = None
            if isinstance(current, WindowsRejected):
                conflict = current
            elif current != initial:
                conflict = WindowsFailure(FailureCode.TARGET_REPLACED, operation, False)
        else:
            conflict = _precondition(absolute, expected_target)
        if conflict is not None:
            result = conflict
        else:
            temporary.replace(absolute)
            temporary = None
            target_replaced = True
            operation = AtomicOperation.DIRECTORY_FSYNC
            injector.before(operation)
            result = WindowsSuccess(len(data))
    except PermissionError:
        result = WindowsFailure(FailureCode.PERMISSION_DENIED, operation, target_replaced)
    except OSError:
        result = WindowsFailure(FailureCode.FILESYSTEM_ERROR, operation, target_replaced)
    cleanup = _cleanup(temporary, injector)
    return cleanup or result


__all__ = [
    "WindowsFailure",
    "WindowsRejected",
    "WindowsSuccess",
    "atomic_replace_windows",
]
