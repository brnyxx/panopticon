from __future__ import annotations

import errno
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from panopticon.store import (
    AtomicOperation,
    DirectorySyncStatus,
    LeakContext,
    ModelArtifact,
    PersistFailure,
    PersistRejected,
    PersistRequest,
    PersistSuccess,
    RenderField,
    RenderModel,
    SinkKind,
    atomic,
    persist,
)


def _request(target: Path, value: str = "replacement") -> PersistRequest:
    model = RenderModel(
        schema_version="1.0",
        title="Atomic fixture",
        fields=(RenderField(name="value", value=value),),
    )
    return PersistRequest(target, ModelArtifact(SinkKind.JSON, model))


def test_windows_path_backend_replaces_regular_file_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target.json"
    target.write_text("prior", encoding="utf-8")
    monkeypatch.setattr(atomic.os, "name", "nt")

    result = persist(_request(target), LeakContext())

    assert isinstance(result, PersistSuccess)
    assert result.directory_sync is DirectorySyncStatus.UNSUPPORTED
    assert b"replacement" in target.read_bytes()
    assert not tuple(tmp_path.glob("*.tmp"))


@dataclass(frozen=True, slots=True)
class FailingInjector:
    operation: AtomicOperation
    error_number: int = errno.EIO

    def before(self, operation: AtomicOperation) -> None:
        if operation is self.operation:
            raise OSError(self.error_number, operation.value)


@dataclass(frozen=True, slots=True)
class SymlinkSwapInjector:
    operation: AtomicOperation
    target: Path
    referent: Path

    def before(self, operation: AtomicOperation) -> None:
        if operation is self.operation:
            self.target.unlink(missing_ok=True)
            self.target.symlink_to(self.referent)


def test_symlink_target_is_rejected_without_touching_referent(tmp_path: Path) -> None:
    # Given: a destination that is already a symlink.
    referent = tmp_path / "referent"
    referent.write_bytes(b"prior")
    target = tmp_path / "target"
    target.symlink_to(referent)

    # When: persistence reaches the filesystem boundary.
    result = persist(_request(target), LeakContext())

    # Then: the symlink and referent remain untouched with no temp residue.
    assert isinstance(result, PersistRejected)
    assert target.is_symlink()
    assert referent.read_bytes() == b"prior"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["referent", "target"]


def test_symlink_swap_at_replace_boundary_is_rejected(tmp_path: Path) -> None:
    # Given: a regular target swapped to a symlink immediately before replacement.
    referent = tmp_path / "referent"
    referent.write_bytes(b"prior-referent")
    target = tmp_path / "target"
    target.write_bytes(b"prior-target")
    injector = SymlinkSwapInjector(AtomicOperation.REPLACE, target, referent)

    # When: the deterministic boundary hook performs the swap.
    result = persist(_request(target), LeakContext(), injector)

    # Then: replacement rejects the symlink and never touches its referent.
    assert isinstance(result, PersistRejected)
    assert target.is_symlink()
    assert referent.read_bytes() == b"prior-referent"
    assert not any(path.name.startswith(".target.") for path in tmp_path.iterdir())


@pytest.mark.parametrize(
    "operation",
    (
        AtomicOperation.WRITE,
        AtomicOperation.FLUSH,
        AtomicOperation.FILE_FSYNC,
        AtomicOperation.REPLACE,
    ),
)
def test_failure_before_replace_preserves_prior_target_and_cleans_temp(
    operation: AtomicOperation, tmp_path: Path
) -> None:
    # Given: a pre-existing complete target and one injected atomic-stage failure.
    target = tmp_path / "target"
    target.write_bytes(b"prior")

    # When: the selected operation fails deterministically.
    result = persist(_request(target), LeakContext(), FailingInjector(operation))

    # Then: prior bytes remain and no temporary artifact survives.
    assert isinstance(result, PersistFailure)
    assert result.operation is operation
    assert target.read_bytes() == b"prior"
    assert tuple(path.name for path in tmp_path.iterdir()) == ("target",)


def test_directory_fsync_failure_reports_complete_replaced_target(tmp_path: Path) -> None:
    # Given: a target whose replacement succeeds before directory durability fails.
    target = tmp_path / "target"
    target.write_bytes(b"prior")

    # When: directory fsync returns an unexpected I/O failure.
    result = persist(
        _request(target), LeakContext(), FailingInjector(AtomicOperation.DIRECTORY_FSYNC)
    )

    # Then: failure is explicit and the target is a complete canonical artifact.
    assert isinstance(result, PersistFailure)
    assert result.operation is AtomicOperation.DIRECTORY_FSYNC
    assert target.read_bytes().endswith(b"\n")
    assert not any(path.name.startswith(".target.") for path in tmp_path.iterdir())


def test_unsupported_directory_fsync_is_explicit_success(tmp_path: Path) -> None:
    # Given: a platform that explicitly reports directory fsync unsupported.
    target = tmp_path / "target"
    injector = FailingInjector(AtomicOperation.DIRECTORY_FSYNC, errno.EINVAL)

    # When: a complete replacement reaches the unsupported durability operation.
    result = persist(_request(target), LeakContext(), injector)

    # Then: the typed success records the unsupported platform guarantee.
    assert isinstance(result, PersistSuccess)
    assert result.directory_sync is DirectorySyncStatus.UNSUPPORTED


def test_new_and_replaced_targets_have_deterministic_restrictive_mode(tmp_path: Path) -> None:
    # Given: one absent and one permissive pre-existing target.
    first = tmp_path / "first"
    second = tmp_path / "second"
    second.write_bytes(b"prior")
    second.chmod(0o644)

    # When: both targets are persisted.
    first_result = persist(_request(first), LeakContext())
    second_result = persist(_request(second), LeakContext())

    # Then: same-directory replacement fixes both modes at 0600.
    assert isinstance(first_result, PersistSuccess)
    assert isinstance(second_result, PersistSuccess)
    assert first.stat().st_mode & 0o777 == 0o600
    assert second.stat().st_mode & 0o777 == 0o600


def test_symlink_parent_component_is_rejected_without_write(tmp_path: Path) -> None:
    # Given: a destination parent that resolves through a symlink.
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    # When: persistence attempts to traverse the linked parent.
    result = persist(_request(linked_parent / "target"), LeakContext())

    # Then: traversal is rejected and the referent directory stays empty.
    assert isinstance(result, PersistRejected)
    assert tuple(real_parent.iterdir()) == ()


def test_short_descriptor_writes_are_completed_without_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a descriptor writer that accepts only a short prefix on each call.
    target = tmp_path / "target"
    original_write = os.write
    limits = iter((1, 2, 3, 5, 8, 13, 21, 34, 55, 89))
    calls: list[int] = []

    def short_write(descriptor: int, data: bytes) -> int:
        limit = next(limits, len(data))
        calls.append(min(limit, len(data)))
        return original_write(descriptor, data[:limit])

    monkeypatch.setattr(os, "write", short_write)

    # When: the public gateway persists through the injected short-write sequence.
    result = persist(_request(target), LeakContext())

    # Then: success means multiple writes completed one full canonical artifact.
    assert isinstance(result, PersistSuccess)
    assert len(calls) > 1
    assert sum(calls) == result.bytes_written
    assert len(target.read_bytes()) == result.bytes_written
    assert target.read_bytes().endswith(b"\n")


def test_eintr_descriptor_write_is_retried_to_complete_canonical_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a descriptor writer that interrupts once and then writes short prefixes.
    target = tmp_path / "target"
    original_write = os.write
    interruption_count = 0
    partial_write_lengths: list[int] = []

    def interrupted_once(descriptor: int, data: bytes) -> int:
        nonlocal interruption_count
        if interruption_count == 0:
            interruption_count += 1
            raise InterruptedError(errno.EINTR, "interrupted")
        chunk = data[:3]
        partial_write_lengths.append(len(chunk))
        return original_write(descriptor, chunk)

    monkeypatch.setattr(os, "write", interrupted_once)
    expected = (
        b'{"fields":[{"name":"value","value":"interrupted"}],'
        b'"schema_version":"1.0","title":"Atomic fixture"}\n'
    )

    # When: persistence reaches the interrupted descriptor write.
    result = persist(_request(target, "interrupted"), LeakContext())

    # Then: EINTR is retried and all canonical bytes remain in the target with no residue.
    assert isinstance(result, PersistSuccess)
    assert interruption_count == 1
    assert len(partial_write_lengths) > 1
    assert result.bytes_written == len(expected)
    assert target.read_bytes() == expected
    assert tuple(tmp_path.iterdir()) == (target,)


def test_zero_descriptor_write_returns_typed_failure_without_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a descriptor writer that makes no forward progress.
    target = tmp_path / "target"

    def zero_write(descriptor: int, data: bytes) -> int:
        return 0

    monkeypatch.setattr(os, "write", zero_write)

    # When: persistence attempts the complete-write loop.
    result = persist(_request(target), LeakContext())

    # Then: truncation is never reported as success and temp residue is removed.
    assert isinstance(result, PersistFailure)
    assert result.operation is AtomicOperation.WRITE
    assert not target.exists()
    assert tuple(tmp_path.iterdir()) == ()
