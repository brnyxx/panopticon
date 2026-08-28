"""Backup, journal, and hash-checked restore helpers for fix execution."""

from __future__ import annotations

import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from panopticon.models.common import NonEmptyStr, PersistedPathValue, StrictModel
from panopticon.secrets.backup import save_encrypted_backup
from panopticon.secrets.contracts import BackupSaved, SecretStore
from panopticon.store.atomic import AtomicSuccess, atomic_replace
from panopticon.store.contracts import (
    AtomicPrecondition,
    BinaryArtifact,
    ModelArtifact,
    PersistRequest,
    PersistSuccess,
    RenderField,
    RenderModel,
    SinkKind,
)
from panopticon.store.repository import ArtifactRepository
from panopticon.util.leak_check import LeakContext, find_leaks

from .backup import backup_target, encrypted_backup_request
from .model import BackupRequest, FixPlan, digest


class MutationIdentity(Protocol):
    @property
    def fix_id(self) -> str: ...


class JournalStatus(StrEnum):
    BACKED_UP = "BACKED_UP"
    APPLIED = "APPLIED"
    RECHECKED = "RECHECKED"
    ROLLED_BACK = "ROLLED_BACK"
    UNDONE = "UNDONE"


class FixJournal(StrictModel):
    schema_version: Literal["0.1"] = "0.1"
    transaction_id: NonEmptyStr
    fix_id: NonEmptyStr
    config_path: PersistedPathValue
    backup_name: NonEmptyStr
    original_hash: NonEmptyStr
    apply_hash: NonEmptyStr
    encrypted: bool
    mode: int
    status: JournalStatus


@dataclass(frozen=True, slots=True)
class StoredBackup:
    target: Path
    encrypted: bool


def _render_model(plan: FixPlan) -> RenderModel:
    return RenderModel(
        schema_version="0.1",
        title="Panopticon fix backup",
        fields=(RenderField(name="config_path", value=str(plan.logical_target)),),
    )


def persist_backup(
    repository: ArtifactRepository,
    store: SecretStore | None,
    plan: FixPlan,
    selection: MutationIdentity,
    transaction_id: str,
    context: LeakContext,
) -> StoredBackup | None:
    target = backup_target(repository.root / "fix" / "backups" / transaction_id, "backup")
    try:
        scan_text = plan.original.decode(plan.encoding)
    except (LookupError, UnicodeError):
        scan_text = ""
        decode_failed = True
    else:
        decode_failed = False
    needs_encryption = (
        selection.fix_id == "FIX-001" or decode_failed or bool(find_leaks(scan_text, context))
    )
    if needs_encryption:
        if store is None:
            return None
        request = encrypted_backup_request(
            BackupRequest(
                target,
                plan.logical_target,
                plan.original,
                "fix",
                plan.original_hash,
            ),
            context,
        )
        saved = save_encrypted_backup(request, store, repository.persist_request)
        return StoredBackup(target, True) if isinstance(saved, BackupSaved) else None
    persisted = repository.persist_request(
        PersistRequest(
            target,
            BinaryArtifact(SinkKind.BACKUP, _render_model(plan), plan.original),
        ),
        context,
    )
    return StoredBackup(target, False) if isinstance(persisted, PersistSuccess) else None


def journal_target(repository: ArtifactRepository, transaction_id: str) -> Path:
    return repository.root / "fix" / "journal" / f"{transaction_id}.json"


def persist_journal(repository: ArtifactRepository, journal: FixJournal) -> bool:
    result = repository.persist_request(
        PersistRequest(
            journal_target(repository, journal.transaction_id),
            ModelArtifact(SinkKind.JOURNAL, journal),
        )
    )
    return isinstance(result, PersistSuccess)


def snapshot(target: Path) -> tuple[bytes, tuple[int, int], int] | None:
    try:
        before = target.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            return None
        data = target.read_bytes()
        after = target.lstat()
    except OSError:
        return None
    identity = before.st_dev, before.st_ino
    if identity != (after.st_dev, after.st_ino):
        return None
    return data, identity, stat.S_IMODE(after.st_mode)


def restore(target: Path, expected_hash: str, original: bytes, mode: int) -> bool:
    current = snapshot(target)
    if current is None:
        return False
    data, identity, _current_mode = current
    if digest(data) != expected_hash:
        return False
    restored = atomic_replace(
        target,
        original,
        expected_target=AtomicPrecondition(identity, expected_hash),
        mode=mode,
    )
    return isinstance(restored, AtomicSuccess)


__all__ = [
    "FixJournal",
    "JournalStatus",
    "StoredBackup",
    "journal_target",
    "persist_backup",
    "persist_journal",
    "restore",
    "snapshot",
]
