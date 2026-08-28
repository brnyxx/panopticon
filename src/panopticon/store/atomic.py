"""Symlink-safe same-directory atomic replacement with explicit durability."""

from __future__ import annotations

import errno
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeAlias

from panopticon.store.contracts import (
    AtomicConflict,
    AtomicConflictReason,
    AtomicOperation,
    AtomicPrecondition,
    DirectorySyncStatus,
    FailureCode,
    FaultInjector,
    RejectionCode,
    TargetIdentity,
)

_UNSUPPORTED_DIR_FSYNC: Final[frozenset[int]] = frozenset(
    {
        errno.EINVAL,
        getattr(errno, "ENOTSUP", errno.EINVAL),
        getattr(errno, "EOPNOTSUPP", errno.EINVAL),
    }
)


class NoFaults:
    def before(self, operation: AtomicOperation) -> None:
        """Leave the real operation untouched."""


@dataclass(frozen=True, slots=True)
class AtomicSuccess:
    bytes_written: int
    directory_sync: DirectorySyncStatus


@dataclass(frozen=True, slots=True)
class AtomicRejected:
    code: RejectionCode


@dataclass(frozen=True, slots=True)
class AtomicFailure:
    code: FailureCode
    operation: AtomicOperation
    target_replaced: bool


AtomicResult: TypeAlias = AtomicSuccess | AtomicRejected | AtomicFailure | AtomicConflict


@dataclass(frozen=True, slots=True)
class UnsafePathError(Exception):
    code: RejectionCode

    def __str__(self) -> str:
        return self.code.value


def _open_parent(target: Path, injector: FaultInjector) -> int:
    injector.before(AtomicOperation.OPEN_PARENT)
    absolute = target.absolute()
    parent_parts = absolute.parent.parts
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(parent_parts[0], flags)
    try:
        for component in parent_parts[1:]:
            next_descriptor = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
    except OSError as error:
        os.close(descriptor)
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise UnsafePathError(RejectionCode.UNSAFE_PARENT) from error
        raise
    return descriptor


def _check_target(directory_fd: int, name: str) -> tuple[int, int] | None:
    try:
        target_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(target_stat.st_mode):
        raise UnsafePathError(RejectionCode.SYMLINK_TARGET)
    if not stat.S_ISREG(target_stat.st_mode):
        raise UnsafePathError(RejectionCode.UNSAFE_TARGET)
    return target_stat.st_dev, target_stat.st_ino


def _check_precondition(
    directory_fd: int, name: str, expected: AtomicPrecondition
) -> AtomicConflict | None:
    """Compare target identity before reading and hashing its current bytes."""
    try:
        target_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return AtomicConflict(AtomicConflictReason.IDENTITY_CHANGED, AtomicOperation.REPLACE)
    if stat.S_ISLNK(target_stat.st_mode):
        raise UnsafePathError(RejectionCode.SYMLINK_TARGET)
    if not stat.S_ISREG(target_stat.st_mode):
        raise UnsafePathError(RejectionCode.UNSAFE_TARGET)
    identity = target_stat.st_dev, target_stat.st_ino
    if identity != expected.identity:
        return AtomicConflict(AtomicConflictReason.IDENTITY_CHANGED, AtomicOperation.REPLACE)

    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            opened_stat = os.fstat(stream.fileno())
            opened_identity: TargetIdentity = opened_stat.st_dev, opened_stat.st_ino
            if opened_identity != expected.identity:
                return AtomicConflict(
                    AtomicConflictReason.IDENTITY_CHANGED, AtomicOperation.REPLACE
                )
            digest = hashlib.sha256(stream.read()).hexdigest()
    except FileNotFoundError:
        return AtomicConflict(AtomicConflictReason.IDENTITY_CHANGED, AtomicOperation.REPLACE)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise UnsafePathError(RejectionCode.SYMLINK_TARGET) from error
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if digest != expected.sha256:
        return AtomicConflict(AtomicConflictReason.CONTENT_CHANGED, AtomicOperation.REPLACE)
    return None


def _cleanup(
    directory_fd: int, temporary_name: str | None, injector: FaultInjector
) -> AtomicFailure | None:
    if temporary_name is None:
        return None
    injected_failure: AtomicFailure | None = None
    try:
        injector.before(AtomicOperation.CLEANUP)
    except PermissionError:
        injected_failure = AtomicFailure(
            FailureCode.PERMISSION_DENIED, AtomicOperation.CLEANUP, False
        )
    except OSError:
        injected_failure = AtomicFailure(FailureCode.CLEANUP_ERROR, AtomicOperation.CLEANUP, False)
    try:
        os.unlink(temporary_name, dir_fd=directory_fd)
    except FileNotFoundError:
        return injected_failure
    except PermissionError:
        return AtomicFailure(FailureCode.PERMISSION_DENIED, AtomicOperation.CLEANUP, False)
    except OSError:
        return AtomicFailure(FailureCode.CLEANUP_ERROR, AtomicOperation.CLEANUP, False)
    return injected_failure


def atomic_replace(
    target: Path,
    data: bytes,
    injector: FaultInjector | None = None,
    *,
    expected_target: AtomicPrecondition | None = None,
    mode: int = 0o600,
) -> AtomicResult:
    """Replace a regular target without following any parent or target symlink."""
    if mode <= 0 or mode & ~0o777:
        return AtomicRejected(RejectionCode.UNSAFE_TARGET)
    active_injector = injector if injector is not None else NoFaults()
    directory_fd = -1
    temporary_name: str | None = None
    operation = AtomicOperation.OPEN_PARENT
    target_replaced = False
    target_identity: tuple[int, int] | None = None
    result: AtomicResult
    try:
        directory_fd = _open_parent(target, active_injector)
        target_identity = _check_target(directory_fd, target.name)
        operation = AtomicOperation.CREATE_TEMP
        active_injector.before(operation)
        temporary_name = f".{target.name}.{os.urandom(8).hex()}.tmp"
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        file_descriptor = os.open(temporary_name, flags, 0o600, dir_fd=directory_fd)
        try:
            os.fchmod(file_descriptor, mode)
            operation = AtomicOperation.WRITE
            active_injector.before(operation)
            offset = 0
            while offset < len(data):
                try:
                    written = os.write(file_descriptor, data[offset:])
                except InterruptedError:
                    continue
                if written <= 0:
                    raise OSError(errno.EIO, "descriptor write made no progress")
                offset += written
            operation = AtomicOperation.FLUSH
            active_injector.before(operation)
            operation = AtomicOperation.FILE_FSYNC
            active_injector.before(operation)
            os.fsync(file_descriptor)
        finally:
            os.close(file_descriptor)
        operation = AtomicOperation.REPLACE
        active_injector.before(operation)
        if expected_target is None:
            current_identity = _check_target(directory_fd, target.name)
            conflict: AtomicResult | None = None
            if current_identity != target_identity:
                conflict = AtomicFailure(FailureCode.TARGET_REPLACED, operation, False)
        else:
            conflict = _check_precondition(directory_fd, target.name, expected_target)
        if conflict is not None:
            result = conflict
        else:
            os.replace(
                temporary_name,
                target.name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
            temporary_name = None
            target_replaced = True
            operation = AtomicOperation.DIRECTORY_FSYNC
            try:
                active_injector.before(operation)
                os.fsync(directory_fd)
            except PermissionError:
                result = AtomicFailure(FailureCode.PERMISSION_DENIED, operation, True)
            except OSError as error:
                if error.errno in _UNSUPPORTED_DIR_FSYNC:
                    result = AtomicSuccess(len(data), DirectorySyncStatus.UNSUPPORTED)
                else:
                    result = AtomicFailure(FailureCode.FILESYSTEM_ERROR, operation, True)
            else:
                result = AtomicSuccess(len(data), DirectorySyncStatus.SYNCED)
    except UnsafePathError as error:
        result = AtomicRejected(error.code)
    except PermissionError:
        result = AtomicFailure(FailureCode.PERMISSION_DENIED, operation, target_replaced)
    except OSError:
        result = AtomicFailure(FailureCode.FILESYSTEM_ERROR, operation, target_replaced)
    if directory_fd >= 0:
        cleanup_failure = _cleanup(directory_fd, temporary_name, active_injector)
        try:
            os.close(directory_fd)
        except OSError:
            cleanup_failure = AtomicFailure(
                FailureCode.CLEANUP_ERROR, AtomicOperation.CLEANUP, target_replaced
            )
        if cleanup_failure is not None:
            return cleanup_failure
    return result
