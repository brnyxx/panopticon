from __future__ import annotations

from pathlib import Path

import pytest

from ._support import (
    JSONC_SOURCE,
    AtomicOperation,
    CleanupFailureInjector,
    DocumentSpec,
    FailingInjector,
    PatchSpec,
    PermissionInjector,
    ReplacementInjector,
    WriteSpec,
    apply_patches,
    assert_no_temp_residue,
    machine_value,
    make_patch,
    parse_document,
    require_jsonc_api,
    require_jsonc_module,
    write_source,
)


def test_replacement_identity_is_rejected_even_when_bytes_match(tmp_path: Path) -> None:
    # Given: a parsed file replaced by a different inode containing identical bytes.
    target = tmp_path / "config.jsonc"
    write_source(target)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(JSONC_SOURCE, target))
    replacement_dir = tmp_path / "replacement"
    replacement_dir.mkdir()
    replacement = replacement_dir / "config.jsonc"
    write_source(replacement)
    replacement.replace(target)
    patch = make_patch(api, PatchSpec("REPLACE", "/mcpServers/fixture/command", "node"))

    # When: the old source document is submitted to the write transaction.
    result = apply_patches(api, WriteSpec(target, document, (patch,)))

    # Then: identity conflict wins over equal content and writes zero bytes.
    assert machine_value(result.status) == "CONFLICT"
    assert machine_value(result.reason_code) == "SOURCE_REPLACED"
    assert result.bytes_written == 0
    assert target.read_bytes() == JSONC_SOURCE
    assert tuple(sorted(path.name for path in tmp_path.iterdir())) == (
        target.name,
        replacement_dir.name,
    )


def test_symlink_target_change_is_rejected_without_following_referent(tmp_path: Path) -> None:
    # Given: a parsed regular file changed to a symlink before patch application.
    target = tmp_path / "config.jsonc"
    referent = tmp_path / "referent.jsonc"
    write_source(target)
    referent.write_bytes(b"referent-bytes")
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(JSONC_SOURCE, target))
    target.unlink()
    target.symlink_to(referent)
    patch = make_patch(api, PatchSpec("REPLACE", "/mcpServers/fixture/command", "node"))

    # When: the stale document reaches the symlink-safe write boundary.
    result = apply_patches(api, WriteSpec(target, document, (patch,)))

    # Then: the link is rejected and its referent remains byte-for-byte untouched.
    assert machine_value(result.status) == "REJECTED"
    assert machine_value(result.reason_code) == "SYMLINK_TARGET"
    assert result.bytes_written == 0
    assert target.is_symlink()
    assert referent.read_bytes() == b"referent-bytes"
    assert tuple(sorted(path.name for path in tmp_path.iterdir())) == (
        target.name,
        referent.name,
    )


def test_regular_replacement_at_atomic_boundary_is_a_source_conflict(
    tmp_path: Path,
) -> None:
    # Given: a parsed source and a different regular file introduced at replacement time.
    target = tmp_path / "config.jsonc"
    write_source(target)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(JSONC_SOURCE, target))
    replacement_dir = tmp_path / "replacement"
    replacement_dir.mkdir()
    replacement = replacement_dir / "config.jsonc"
    replacement.write_bytes(b"replacement-bytes")
    patch = make_patch(api, PatchSpec("REPLACE", "/mcpServers/fixture/command", "node"))

    # When: the atomic seam replaces the target immediately before its final rename.
    result = apply_patches(
        api,
        WriteSpec(target, document, (patch,)),
        ReplacementInjector(AtomicOperation.REPLACE, target, replacement),
    )

    # Then: the concurrent regular replacement is preserved and reported as a conflict.
    assert machine_value(result.status) == "CONFLICT"
    assert machine_value(result.reason_code) == "SOURCE_REPLACED"
    assert result.bytes_written == 0
    assert target.read_bytes() == b"replacement-bytes"
    assert not any(path.name.startswith(f".{target.name}.") for path in tmp_path.iterdir())


def test_symlink_parent_is_rejected_before_atomic_delegate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a valid source reached through a symlinked parent directory.
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    real_target = real_parent / "config.jsonc"
    write_source(real_target)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(JSONC_SOURCE, real_target))
    patch = make_patch(api, PatchSpec("REPLACE", "/mcpServers/fixture/command", "node"))

    def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("atomic replacement must not receive an unsafe parent")

    transaction = require_jsonc_module("transaction")
    monkeypatch.setattr(transaction, "atomic_replace", fail_if_called)

    # When: the transaction is addressed through the unsafe parent.
    result = apply_patches(
        api,
        WriteSpec(linked_parent / "config.jsonc", document, (patch,)),
    )

    # Then: the secure read boundary rejects traversal before any write delegate.
    assert machine_value(result.status) == "REJECTED"
    assert machine_value(result.reason_code) == "UNSAFE_PARENT"
    assert real_target.read_bytes() == JSONC_SOURCE


def test_read_error_returns_typed_failure_without_a_write(tmp_path: Path) -> None:
    # Given: a parsed file path replaced by a directory before the transaction reads it.
    target = tmp_path / "config.jsonc"
    write_source(target)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(JSONC_SOURCE, target))
    target.unlink()
    target.mkdir()
    patch = make_patch(api, PatchSpec("REPLACE", "/mcpServers/fixture/command", "node"))

    # When: the transaction attempts to read the current source bytes.
    result = apply_patches(api, WriteSpec(target, document, (patch,)))

    # Then: the read failure is typed and no temporary file is created.
    assert machine_value(result.status) == "FAILED"
    assert machine_value(result.reason_code) == "READ_ERROR"
    assert result.bytes_written == 0
    assert target.is_dir()
    assert tuple(path.name for path in tmp_path.iterdir()) == (target.name,)


def test_injected_permission_boundary_returns_typed_failure_without_a_write(
    tmp_path: Path,
) -> None:
    # Given: a valid source and a deterministic Task4 permission boundary injector.
    target = tmp_path / "config.jsonc"
    write_source(target)
    original = target.read_bytes()
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(JSONC_SOURCE, target))
    patch = make_patch(api, PatchSpec("REPLACE", "/mcpServers/fixture/command", "node"))

    # When: CREATE_TEMP is rejected with PermissionError before any temporary bytes exist.
    result = apply_patches(
        api,
        WriteSpec(target, document, (patch,)),
        PermissionInjector(AtomicOperation.CREATE_TEMP),
    )

    # Then: the injected permission failure is typed and the target remains exact.
    assert machine_value(result.status) == "FAILED"
    assert machine_value(result.reason_code) == "PERMISSION_DENIED"
    assert result.bytes_written == 0
    assert target.read_bytes() == original
    assert tuple(path.name for path in tmp_path.iterdir()) == (target.name,)
    assert_no_temp_residue(tmp_path, target)


def test_cleanup_failure_is_typed_and_leaves_no_temp_residue(tmp_path: Path) -> None:
    # Given: a valid source and cleanup failure after a pre-replacement write failure.
    target = tmp_path / "config.jsonc"
    write_source(target)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(JSONC_SOURCE, target))
    patch = make_patch(api, PatchSpec("REPLACE", "/mcpServers/fixture/command", "node"))

    # When: the atomic write fails and cleanup reports its own failure boundary.
    result = apply_patches(
        api,
        WriteSpec(target, document, (patch,)),
        CleanupFailureInjector(AtomicOperation.WRITE),
    )

    # Then: cleanup failure is explicit while the original target and directory stay clean.
    assert machine_value(result.status) == "FAILED"
    assert machine_value(result.reason_code) == "CLEANUP_ERROR"
    assert result.bytes_written == 0
    assert target.read_bytes() == JSONC_SOURCE
    assert_no_temp_residue(tmp_path, target)


def test_atomic_write_failure_preserves_original_target_and_temp_cleanup(
    tmp_path: Path,
) -> None:
    # Given: a valid source and the Task4 fault injector at the atomic write boundary.
    target = tmp_path / "config.jsonc"
    write_source(target)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(JSONC_SOURCE, target))
    patch = make_patch(api, PatchSpec("REPLACE", "/mcpServers/fixture/command", "node"))

    # When: byte-range output reaches an injected atomic write failure.
    result = apply_patches(
        api,
        WriteSpec(target, document, (patch,)),
        FailingInjector(AtomicOperation.WRITE),
    )

    # Then: the typed failure leaves the original bytes and no temporary residue.
    assert machine_value(result.status) == "FAILED"
    assert machine_value(result.reason_code) == "WRITE_ERROR"
    assert result.bytes_written == 0
    assert target.read_bytes() == JSONC_SOURCE
    assert tuple(path.name for path in tmp_path.iterdir()) == (target.name,)
