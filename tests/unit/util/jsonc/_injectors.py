"""Deterministic atomic fault injectors used by JSONC transaction tests."""

from __future__ import annotations

import errno
from dataclasses import dataclass
from pathlib import Path

from panopticon.store import AtomicOperation


@dataclass(frozen=True, slots=True)
class PermissionInjector:
    operation: AtomicOperation

    def before(self, operation: AtomicOperation) -> None:
        """Raise PermissionError at one deterministic Task4 pre-write boundary."""
        if operation is self.operation:
            raise PermissionError(errno.EACCES, f"injected permission failure: {operation.value}")


@dataclass(frozen=True, slots=True)
class FailingInjector:
    operation: AtomicOperation

    def before(self, operation: AtomicOperation) -> None:
        """Raise at one Task4 atomic boundary."""
        if operation is self.operation:
            raise OSError(operation.value)


@dataclass(frozen=True, slots=True)
class ReplacementInjector:
    operation: AtomicOperation
    target: Path
    replacement: Path

    def before(self, operation: AtomicOperation) -> None:
        """Replace the target at one deterministic atomic boundary."""
        if operation is self.operation:
            self.replacement.replace(self.target)


@dataclass(frozen=True, slots=True)
class ConcurrentReplacementInjector:
    operation: AtomicOperation
    target: Path
    replacement: bytes

    def before(self, operation: AtomicOperation) -> None:
        """Replace target bytes in place at one deterministic atomic boundary."""
        if operation is self.operation:
            self.target.write_bytes(self.replacement)


@dataclass(frozen=True, slots=True)
class CleanupFailureInjector:
    primary_operation: AtomicOperation

    def before(self, operation: AtomicOperation) -> None:
        """Fail both a write stage and its subsequent cleanup boundary."""
        if operation in {self.primary_operation, AtomicOperation.CLEANUP}:
            raise OSError(operation.value)
