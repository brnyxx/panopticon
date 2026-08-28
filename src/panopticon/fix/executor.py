"""Backup-first, hash-checked configuration transaction executor."""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Protocol

from panopticon.models.common import PersistedPath
from panopticon.models.ids import JsonPointer
from panopticon.secrets.backup import decrypt_backup
from panopticon.secrets.contracts import BackupDecrypted, BackupDecryptRequest, SecretStore
from panopticon.store.repository import ArtifactRepository
from panopticon.util.jsonc.parser import parse_document
from panopticon.util.jsonc.pointer import decode_pointer, value_at
from panopticon.util.jsonc.transaction import PatchRequest, PatchStatus, apply_patches
from panopticon.util.leak_check import LeakContext

from ._executor_store import (
    FixJournal,
    JournalStatus,
    journal_target,
    persist_backup,
    persist_journal,
    restore,
    snapshot,
)
from .cli_model import FixOutcomeStatus, FixSelection
from .model import FixPlan
from .service import TransactionReceipt
from .transaction import apply, confirm, prepare


class MutationSelection(Protocol):
    @property
    def fix_id(self) -> str: ...

    @property
    def config_path(self) -> Path: ...

    @property
    def pointer(self) -> JsonPointer: ...

    @property
    def value(self) -> str | None: ...

    def bind_transaction(self, plan: FixPlan, transaction_id: str) -> FixPlan: ...


class Rechecker(Protocol):
    def __call__(self, selection: MutationSelection, plan: FixPlan) -> bool: ...


class Clock(Protocol):
    def __call__(self) -> datetime: ...


class SecretProvisioner(Protocol):
    def provision(self, key: str, value: str) -> bool: ...


def _transaction_id(plan: FixPlan, selection: MutationSelection, now: datetime) -> str:
    raw = f"{selection.fix_id}\0{selection.pointer}\0{plan.original_hash}\0{now.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _secret_value(plan: FixPlan, selection: MutationSelection) -> str | None:
    if selection.fix_id != "FIX-001" or selection.value is None:
        return None
    document = parse_document(
        plan.original,
        path=plan.target,
        logical_path=plan.logical_target,
    )
    value = value_at(document.value, decode_pointer(selection.pointer))
    return value if isinstance(value, str) else None


class FixTransactionExecutor:
    def __init__(
        self,
        repository: ArtifactRepository,
        clock: Clock,
        *,
        secret_store: SecretStore | None = None,
        secret_provisioner: SecretProvisioner | None = None,
        leak_context: LeakContext | None = None,
        rechecker: Rechecker | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock
        self.secret_store = secret_store
        self.secret_provisioner = secret_provisioner
        self.leak_context = leak_context or repository.context
        self.rechecker = rechecker

    def apply(
        self,
        plan: FixPlan,
        selection: MutationSelection,
        *,
        recheck: bool,
    ) -> TransactionReceipt:
        # Reject a stale source before creating backup/journal artifacts.  The
        # atomic patch seam checks again at write time to close the race after
        # this preflight.
        current = snapshot(plan.target)
        if current is None:
            return TransactionReceipt(FixOutcomeStatus.CONFLICT, "SOURCE_UNAVAILABLE")
        current_bytes, current_identity, _mode = current
        if plan.source_identity is not None and current_identity != plan.source_identity:
            return TransactionReceipt(FixOutcomeStatus.CONFLICT, "SOURCE_REPLACED")
        if hashlib.sha256(current_bytes).hexdigest() != plan.original_hash:
            return TransactionReceipt(FixOutcomeStatus.CONFLICT, "SOURCE_STALE")
        transaction_id = _transaction_id(plan, selection, self.clock())
        plan = selection.bind_transaction(plan, transaction_id)
        candidate = apply(plan, confirm(prepare(plan)), plan.original)
        if candidate.apply_hash is None:
            return TransactionReceipt(FixOutcomeStatus.CONFLICT, candidate.reason)
        backup = persist_backup(
            self.repository,
            self.secret_store,
            plan,
            selection,
            transaction_id,
            self.leak_context,
        )
        if backup is None:
            return TransactionReceipt(FixOutcomeStatus.GUIDANCE, "BACKUP_UNAVAILABLE")
        mode = plan.mode or 0o600
        journal = FixJournal(
            transaction_id=transaction_id,
            fix_id=selection.fix_id,
            config_path=PersistedPath(plan.logical_target),
            backup_name=backup.target.name,
            original_hash=plan.original_hash,
            apply_hash=candidate.apply_hash,
            encrypted=backup.encrypted,
            mode=mode,
            status=JournalStatus.BACKED_UP,
        )
        if not persist_journal(self.repository, journal):
            return TransactionReceipt(FixOutcomeStatus.FAILED, "JOURNAL_WRITE_FAILED")
        secret = _secret_value(plan, selection)
        if secret is not None and (
            self.secret_provisioner is None
            or selection.value is None
            or not self.secret_provisioner.provision(selection.value, secret)
        ):
            return TransactionReceipt(FixOutcomeStatus.GUIDANCE, "SECRET_PROVISION_FAILED")
        parsed = parse_document(
            plan.original,
            path=plan.target,
            logical_path=plan.logical_target,
        )
        document = replace(parsed, _identity=plan.source_identity)
        patched = apply_patches(PatchRequest(plan.target, document, plan.patches))
        if patched.status is not PatchStatus.COMPLETE:
            return TransactionReceipt(FixOutcomeStatus.CONFLICT, patched.reason_code.value)
        status = JournalStatus.APPLIED
        outcome = FixOutcomeStatus.APPLIED
        if recheck:
            passed = self.rechecker is not None and self.rechecker(selection, plan)
            if passed:
                status, outcome = JournalStatus.RECHECKED, FixOutcomeStatus.RECHECKED
            elif restore(plan.target, candidate.apply_hash, plan.original, mode):
                status, outcome = JournalStatus.ROLLED_BACK, FixOutcomeStatus.ROLLED_BACK
            else:
                return TransactionReceipt(FixOutcomeStatus.CONFLICT, "ROLLBACK_CONFLICT")
        updated = journal.model_copy(update={"status": status})
        if not persist_journal(self.repository, updated):
            if restore(plan.target, candidate.apply_hash, plan.original, mode):
                return TransactionReceipt(FixOutcomeStatus.ROLLED_BACK, "JOURNAL_WRITE_FAILED")
            return TransactionReceipt(FixOutcomeStatus.CONFLICT, "JOURNAL_AND_ROLLBACK_FAILED")
        return TransactionReceipt(
            outcome,
            "TRANSACTION_COMPLETE",
            (plan.target, backup.target, journal_target(self.repository, transaction_id)),
            transaction_id,
        )

    def undo(self, selection: FixSelection) -> TransactionReceipt:
        transaction_id = selection.value or ""
        return self.restore_transaction(transaction_id, selection)

    def preview_restore(self, transaction_id: str, plan: FixPlan) -> FixPlan | None:
        if re.fullmatch(r"[0-9a-f]{20}", transaction_id) is None:
            return None
        journal_path = journal_target(self.repository, transaction_id)
        try:
            journal = FixJournal.model_validate_json(journal_path.read_bytes())
        except (OSError, ValueError):
            return None
        backup_path = self.repository.root / "fix" / "backups" / journal.backup_name
        try:
            backup = backup_path.read_bytes()
        except OSError:
            return None
        if journal.encrypted:
            if self.secret_store is None:
                return None
            decrypted = decrypt_backup(BackupDecryptRequest(backup), self.secret_store)
            if not isinstance(decrypted, BackupDecrypted):
                return None
            original = decrypted.plaintext
        else:
            original = backup
        current = snapshot(plan.target)
        if current is None or hashlib.sha256(current[0]).hexdigest() not in {
            journal.apply_hash,
            journal.original_hash,
        }:
            return None
        return replace(plan, patches=(), exact_replacement=original)

    def restore_transaction(
        self,
        transaction_id: str,
        selection: MutationSelection,
    ) -> TransactionReceipt:
        if re.fullmatch(r"[0-9a-f]{20}", transaction_id) is None:
            return TransactionReceipt(FixOutcomeStatus.GUIDANCE, "INVALID_TRANSACTION_ID")
        journal_path = journal_target(self.repository, transaction_id)
        try:
            journal = FixJournal.model_validate_json(journal_path.read_bytes())
        except (OSError, ValueError):
            return TransactionReceipt(FixOutcomeStatus.GUIDANCE, "JOURNAL_NOT_FOUND")
        backup_path = self.repository.root / "fix" / "backups" / journal.backup_name
        try:
            backup = backup_path.read_bytes()
        except OSError:
            return TransactionReceipt(FixOutcomeStatus.CONFLICT, "BACKUP_NOT_FOUND")
        if journal.encrypted:
            if self.secret_store is None:
                return TransactionReceipt(FixOutcomeStatus.GUIDANCE, "SECURE_STORE_UNAVAILABLE")
            decrypted = decrypt_backup(BackupDecryptRequest(backup), self.secret_store)
            if not isinstance(decrypted, BackupDecrypted):
                return TransactionReceipt(FixOutcomeStatus.CONFLICT, "BACKUP_DECRYPT_FAILED")
            original = decrypted.plaintext
        else:
            original = backup
        current = snapshot(selection.config_path)
        if current is None:
            return TransactionReceipt(FixOutcomeStatus.CONFLICT, "UNDO_CONFLICT")
        if hashlib.sha256(current[0]).hexdigest() != journal.original_hash and not restore(
            selection.config_path,
            journal.apply_hash,
            original,
            journal.mode,
        ):
            return TransactionReceipt(FixOutcomeStatus.CONFLICT, "UNDO_CONFLICT")
        updated = journal.model_copy(update={"status": JournalStatus.UNDONE})
        if not persist_journal(self.repository, updated):
            return TransactionReceipt(FixOutcomeStatus.FAILED, "JOURNAL_WRITE_FAILED")
        return TransactionReceipt(
            FixOutcomeStatus.UNDONE,
            "UNDO_COMPLETE",
            (selection.config_path, journal_path),
            transaction_id,
        )


__all__ = ["FixTransactionExecutor", "MutationSelection", "SecretProvisioner"]
