"""Hash- and identity-checked JSONC transactions over the Task4 atomic seam."""

from __future__ import annotations

import errno
import hashlib
import os
import stat
from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import TypeAlias, assert_never

from panopticon.store import (
    AtomicConflict,
    AtomicConflictReason,
    AtomicOperation,
    AtomicPrecondition,
    FailureCode,
    FaultInjector,
    RejectionCode,
)
from panopticon.store.atomic import (
    AtomicFailure,
    AtomicRejected,
    AtomicSuccess,
    NoFaults,
    UnsafePathError,
    _open_parent,
    atomic_replace,
)

from .parser import SourceDocument
from .patch import JsoncPatch, patch_document

CurrentIdentity: TypeAlias = tuple[int, int]


@unique
class PatchStatus(StrEnum):
    COMPLETE = "COMPLETE"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@unique
class PatchReason(StrEnum):
    PATCH_APPLIED = "PATCH_APPLIED"
    SOURCE_STALE = "SOURCE_STALE"
    SOURCE_REPLACED = "SOURCE_REPLACED"
    SYMLINK_TARGET = "SYMLINK_TARGET"
    UNSAFE_PARENT = "UNSAFE_PARENT"
    UNSAFE_TARGET = "UNSAFE_TARGET"
    READ_ERROR = "READ_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    FILESYSTEM_ERROR = "FILESYSTEM_ERROR"
    WRITE_ERROR = "WRITE_ERROR"
    FLUSH_ERROR = "FLUSH_ERROR"
    FILE_FSYNC_ERROR = "FILE_FSYNC_ERROR"
    REPLACE_ERROR = "REPLACE_ERROR"
    DIRECTORY_FSYNC_ERROR = "DIRECTORY_FSYNC_ERROR"
    CLEANUP_ERROR = "CLEANUP_ERROR"


@dataclass(frozen=True, slots=True)
class PatchRequest:
    target: Path
    document: SourceDocument
    patches: tuple[JsoncPatch, ...]


@dataclass(frozen=True, slots=True)
class PatchResult:
    target: Path
    status: PatchStatus
    reason_code: PatchReason
    bytes_written: int


def _result(
    target: Path, status: PatchStatus, reason: PatchReason, written: int = 0
) -> PatchResult:
    return PatchResult(target, status, reason, written)


def _read_current(request: PatchRequest) -> CurrentIdentity | PatchResult:
    directory_fd = -1
    descriptor = -1
    try:
        try:
            directory_fd = _open_parent(request.target, NoFaults())
        except UnsafePathError:
            return _result(request.target, PatchStatus.REJECTED, PatchReason.UNSAFE_PARENT)
        stat_result = os.stat(
            request.target.name,
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
        if stat.S_ISLNK(stat_result.st_mode):
            return _result(request.target, PatchStatus.REJECTED, PatchReason.SYMLINK_TARGET)
        if not stat.S_ISREG(stat_result.st_mode):
            return _result(request.target, PatchStatus.FAILED, PatchReason.READ_ERROR)
        identity = stat_result.st_dev, stat_result.st_ino
        if request.document.identity is not None and identity != request.document.identity:
            return _result(request.target, PatchStatus.CONFLICT, PatchReason.SOURCE_REPLACED)

        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(request.target.name, flags, dir_fd=directory_fd)
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            opened_stat = os.fstat(stream.fileno())
            opened_identity = opened_stat.st_dev, opened_stat.st_ino
            if opened_identity != identity:
                return _result(request.target, PatchStatus.CONFLICT, PatchReason.SOURCE_REPLACED)
            data = stream.read()
    except FileNotFoundError:
        return _result(request.target, PatchStatus.FAILED, PatchReason.READ_ERROR)
    except PermissionError:
        return _result(request.target, PatchStatus.FAILED, PatchReason.PERMISSION_DENIED)
    except OSError as error:
        if error.errno == errno.ELOOP:
            return _result(request.target, PatchStatus.REJECTED, PatchReason.SYMLINK_TARGET)
        return _result(request.target, PatchStatus.FAILED, PatchReason.READ_ERROR)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if directory_fd >= 0:
            os.close(directory_fd)
    if hashlib.sha256(data).hexdigest() != request.document.original_sha256:
        return _result(request.target, PatchStatus.CONFLICT, PatchReason.SOURCE_STALE)
    return identity


def _failure_reason(result: AtomicFailure) -> PatchReason:
    operation_reasons = {
        AtomicOperation.OPEN_PARENT: PatchReason.FILESYSTEM_ERROR,
        AtomicOperation.CREATE_TEMP: PatchReason.FILESYSTEM_ERROR,
        AtomicOperation.WRITE: PatchReason.WRITE_ERROR,
        AtomicOperation.FLUSH: PatchReason.FLUSH_ERROR,
        AtomicOperation.FILE_FSYNC: PatchReason.FILE_FSYNC_ERROR,
        AtomicOperation.REPLACE: PatchReason.REPLACE_ERROR,
        AtomicOperation.DIRECTORY_FSYNC: PatchReason.DIRECTORY_FSYNC_ERROR,
        AtomicOperation.CLEANUP: PatchReason.CLEANUP_ERROR,
    }
    match result.code:
        case FailureCode.PERMISSION_DENIED:
            return PatchReason.PERMISSION_DENIED
        case FailureCode.TARGET_REPLACED:
            return PatchReason.SOURCE_REPLACED
        case FailureCode.FILESYSTEM_ERROR | FailureCode.CLEANUP_ERROR:
            return operation_reasons[result.operation]
        case unreachable:
            assert_never(unreachable)


def _rejection_reason(code: RejectionCode) -> PatchReason:
    match code:
        case RejectionCode.UNSAFE_PARENT:
            return PatchReason.UNSAFE_PARENT
        case RejectionCode.SYMLINK_TARGET:
            return PatchReason.SYMLINK_TARGET
        case RejectionCode.UNSAFE_TARGET:
            return PatchReason.UNSAFE_TARGET
        case RejectionCode.LEAK_DETECTED | RejectionCode.INVALID_ARTIFACT:
            return PatchReason.FILESYSTEM_ERROR
        case unreachable:
            assert_never(unreachable)


def apply_patches(request: PatchRequest, injector: FaultInjector | None = None) -> PatchResult:
    """Check source identity twice, patch in memory, then delegate the only write."""
    current = _read_current(request)
    if isinstance(current, PatchResult):
        return current
    patched = patch_document(request.document, request.patches)
    verified = _read_current(request)
    if isinstance(verified, PatchResult):
        return verified
    atomic_result = atomic_replace(
        request.target,
        patched,
        injector,
        expected_target=AtomicPrecondition(verified, request.document.original_sha256),
    )
    match atomic_result:
        case AtomicSuccess():
            return _result(
                request.target, PatchStatus.COMPLETE, PatchReason.PATCH_APPLIED, len(patched)
            )
        case AtomicRejected(code=code):
            return _result(
                request.target,
                PatchStatus.REJECTED,
                _rejection_reason(code),
            )
        case AtomicConflict(reason=reason):
            match reason:
                case AtomicConflictReason.IDENTITY_CHANGED:
                    return _result(
                        request.target, PatchStatus.CONFLICT, PatchReason.SOURCE_REPLACED
                    )
                case AtomicConflictReason.CONTENT_CHANGED:
                    return _result(request.target, PatchStatus.CONFLICT, PatchReason.SOURCE_STALE)
                case unreachable_reason:
                    assert_never(unreachable_reason)
        case AtomicFailure(code=FailureCode.TARGET_REPLACED):
            return _result(request.target, PatchStatus.CONFLICT, PatchReason.SOURCE_REPLACED)
        case AtomicFailure() as failure:
            written = len(patched) if failure.target_replaced else 0
            return _result(request.target, PatchStatus.FAILED, _failure_reason(failure), written)
        case unreachable:
            assert_never(unreachable)
