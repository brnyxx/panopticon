"""Wave 4 acceptance tests for fail-closed fix transactions."""

import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from panopticon.fix.cli_model import FixOutcomeStatus, FixSelection
from panopticon.fix.executor import FixTransactionExecutor
from panopticon.fix.journal import append_value, parse_value
from panopticon.fix.model import FixPrompt, FixState
from panopticon.fix.plan import make_plan
from panopticon.fix.transaction import (
    FixConflictError,
    apply,
    confirm,
    prepare,
    recheck,
    rollback,
    undo,
)
from panopticon.models.ids import ConfigPath, JsonPointer
from panopticon.secrets import InMemorySecretStore
from panopticon.store.repository import ArtifactRepository
from panopticon.util.jsonc.parser import parse_document
from panopticon.util.jsonc.patch import JsoncPatch, PatchOperation
from panopticon.util.jsonc.transaction import PatchRequest, PatchStatus, apply_patches
from panopticon.util.leak_check import LeakContext


def test_concurrent_edit_survives_apply_and_rollback(tmp_path: Path) -> None:
    original = b'{"value": 1, "unknown": true}\n'
    target = tmp_path / "config.jsonc"
    target.write_bytes(original)
    target.chmod(0o640)
    document = parse_document(original, path=target, logical_path=ConfigPath("~/config.jsonc"))
    patch = JsoncPatch(PatchOperation.REPLACE, JsonPointer("/value"), 2)
    plan = make_plan(target, document, (patch,), (FixPrompt("approval"),), mode=0o640)
    result = prepare(plan)
    assert result.state is FixState.PLANNED
    assert result.original_hash == plan.original_hash
    assert result.plan_hash

    declined = confirm(result, approved=False)
    assert declined.state is FixState.PLANNED
    assert declined.reason == "NOT_CONFIRMED"
    confirmed = confirm(result)
    stale_apply = apply(plan, confirmed, b'{"value": 9, "unknown": true}\n')
    assert stale_apply.state is FixState.CONFLICT
    assert stale_apply.reason == "SOURCE_STALE"
    applied = apply(plan, confirmed, original)
    assert applied.state is FixState.APPLIED
    assert applied.apply_hash and applied.current_hash == result.original_hash
    assert applied.bytes_value == b'{"value": 2, "unknown": true}\n'
    persisted = apply_patches(PatchRequest(target, document, (patch,)))
    assert persisted.status is PatchStatus.COMPLETE
    assert target.read_bytes() == applied.bytes_value
    assert stat.S_IMODE(target.stat().st_mode) == 0o640

    # A concurrent edit is a hard conflict at every boundary, never silently merged.
    concurrent = b'{"value": 2, "unknown": false}\n'
    conflict_recheck = recheck(applied, concurrent, passed=True)
    assert conflict_recheck.state is FixState.CONFLICT
    assert conflict_recheck.reason == "USER_CHANGED"
    conflict_rollback = rollback(applied, concurrent, original)
    assert conflict_rollback.state is FixState.CONFLICT
    conflict_undo = undo(applied, concurrent, original)
    assert conflict_undo.state is FixState.CONFLICT

    checked = recheck(applied, applied.bytes_value or b"", passed=False)
    assert checked.state is FixState.RECHECKED
    assert checked.reason == "RECHECK_FAILED"
    rolled = rollback(checked, applied.bytes_value or b"", original)
    assert rolled.state is FixState.ROLLED_BACK
    assert rolled.bytes_value == original
    undone = undo(applied, applied.bytes_value or b"", original)
    assert undone.state is FixState.UNDONE
    assert undone.bytes_value == original
    bad_backup = rollback(checked, applied.bytes_value or b"", b"wrong")
    assert bad_backup.state is FixState.CONFLICT
    assert bad_backup.reason == "BACKUP_MISMATCH"

    tx = "tx-wave4"
    journal = append_value(tx, checked)
    assert b"raw-token" not in journal
    parsed = parse_value(journal)
    assert len(parsed) == 1
    assert parsed[0].transaction_id == tx
    assert parsed[0].state is FixState.RECHECKED
    assert parsed[0].original_hash == result.original_hash
    assert parsed[0].apply_hash == applied.apply_hash

    with pytest.raises(FixConflictError, match="INVALID_STATE"):
        apply(plan, result, original)
    with pytest.raises(FixConflictError, match="INVALID_STATE"):
        confirm(applied)
    with pytest.raises(FixConflictError, match="INVALID_STATE"):
        recheck(result, original, passed=True)
    with pytest.raises(FixConflictError, match="INVALID_STATE"):
        rollback(result, original, original)
    with pytest.raises(FixConflictError, match="INVALID_STATE"):
        undo(rolled, original, original)


def test_secret_fix_backup_is_encrypted_and_undo_is_exact(tmp_path: Path) -> None:
    token = "ghp_fixture_secret_value_123456"
    original = f'{{"env":{{"TOKEN":"{token}"}}}}\n'.encode()
    target = tmp_path / "config.jsonc"
    target.write_bytes(original)
    document = parse_document(
        original,
        path=target,
        logical_path=ConfigPath("~/config.jsonc"),
    )
    patch = JsoncPatch(
        PatchOperation.REPLACE,
        JsonPointer("/env/TOKEN"),
        "${TOKEN}",
    )
    plan = make_plan(target, document, (patch,))
    selection = FixSelection(
        "FIX-001",
        target,
        JsonPointer("/env/TOKEN"),
        value="TOKEN",
    )

    class Provisioner:
        def __init__(self) -> None:
            self.value = ""

        def provision(self, key: str, value: str) -> bool:
            assert key == "TOKEN"
            self.value = value
            return True

    provisioner = Provisioner()
    repository = ArtifactRepository(
        tmp_path / "state",
        LeakContext(secrets=(token,)),
    )
    executor = FixTransactionExecutor(
        repository,
        lambda: datetime(2026, 8, 28, tzinfo=UTC),
        secret_store=InMemorySecretStore(),
        secret_provisioner=provisioner,
        leak_context=LeakContext(secrets=(token,)),
        rechecker=lambda _selection, _plan: target.read_text().endswith('"${TOKEN}"}}\n'),
    )
    applied = executor.apply(plan, selection, recheck=True)
    assert applied.status is FixOutcomeStatus.RECHECKED
    assert applied.transaction_id is not None
    assert provisioner.value == token
    persisted = tuple(path.read_bytes() for path in applied.written_paths[1:])
    assert all(token.encode() not in value for value in persisted)

    undone = executor.undo(
        FixSelection(
            "FIX-001",
            target,
            JsonPointer(""),
            value=applied.transaction_id,
        )
    )
    assert undone.status is FixOutcomeStatus.UNDONE
    assert target.read_bytes() == original
