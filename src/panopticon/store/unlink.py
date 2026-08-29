"""Symlink-safe deletion for repository-owned regular files."""

from __future__ import annotations

import errno
import os
import stat
from enum import StrEnum
from pathlib import Path


class UnlinkStatus(StrEnum):
    REMOVED = "REMOVED"
    NOT_FOUND = "NOT_FOUND"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class ReadStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_FOUND = "NOT_FOUND"
    PERMISSION = "PERMISSION"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


def _open_parent(path: Path) -> int:
    absolute = path.absolute()
    parts = absolute.parent.parts
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(parts[0], flags)
    try:
        for component in parts[1:]:
            next_descriptor = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _unlink_posix(path: Path) -> UnlinkStatus:
    descriptor = -1
    try:
        descriptor = _open_parent(path)
        metadata = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode):
            return UnlinkStatus.REJECTED
        os.unlink(path.name, dir_fd=descriptor)
        os.fsync(descriptor)
        return UnlinkStatus.REMOVED
    except FileNotFoundError:
        return UnlinkStatus.NOT_FOUND
    except PermissionError:
        return UnlinkStatus.REJECTED
    except OSError as error:
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            return UnlinkStatus.REJECTED
        return UnlinkStatus.FAILED
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _unlink_windows(path: Path) -> UnlinkStatus:
    try:
        current = path.parent
        while current != current.parent:
            if current.is_symlink():
                return UnlinkStatus.REJECTED
            current = current.parent
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            return UnlinkStatus.REJECTED
        path.unlink()
        return UnlinkStatus.REMOVED
    except FileNotFoundError:
        return UnlinkStatus.NOT_FOUND
    except PermissionError:
        return UnlinkStatus.REJECTED
    except OSError:
        return UnlinkStatus.FAILED


def unlink_regular(path: Path) -> UnlinkStatus:
    """Delete one regular file without following target or parent symlinks."""
    return _unlink_windows(path) if os.name == "nt" else _unlink_posix(path)


def read_regular(path: Path) -> tuple[ReadStatus, bytes | None]:
    """Read one regular file without following target or parent symlinks."""
    if os.name == "nt":
        try:
            current = path.parent
            while current != current.parent:
                if current.is_symlink():
                    return ReadStatus.REJECTED, None
                current = current.parent
            if not stat.S_ISREG(path.lstat().st_mode):
                return ReadStatus.REJECTED, None
            return ReadStatus.AVAILABLE, path.read_bytes()
        except FileNotFoundError:
            return ReadStatus.NOT_FOUND, None
        except PermissionError:
            return ReadStatus.PERMISSION, None
        except OSError:
            return ReadStatus.FAILED, None
    descriptor = -1
    file_descriptor = -1
    try:
        descriptor = _open_parent(path)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        file_descriptor = os.open(path.name, flags, dir_fd=descriptor)
        if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
            return ReadStatus.REJECTED, None
        with os.fdopen(file_descriptor, "rb") as stream:
            file_descriptor = -1
            return ReadStatus.AVAILABLE, stream.read()
    except FileNotFoundError:
        return ReadStatus.NOT_FOUND, None
    except PermissionError:
        return ReadStatus.PERMISSION, None
    except OSError as error:
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            return ReadStatus.REJECTED, None
        return ReadStatus.FAILED, None
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        if descriptor >= 0:
            os.close(descriptor)


__all__ = ["ReadStatus", "UnlinkStatus", "read_regular", "unlink_regular"]
