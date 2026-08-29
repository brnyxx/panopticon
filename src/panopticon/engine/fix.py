"""Discovery, selection, planning, and transaction composition for `pano fix`."""

from __future__ import annotations

import os
import platform
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from panopticon.discovery.base import DiscoveryEnv
from panopticon.engine.fix_select import (
    FixCommandRequest,
    matching_entries,
)
from panopticon.engine.fix_select import (
    selection as build_selection,
)
from panopticon.fix._executor_store import FixJournal
from panopticon.fix.cli_model import (
    FixBatchOutcome,
    FixOutcome,
    FixOutcomeStatus,
    FixRequest,
    FixSelection,
)
from panopticon.fix.executor import FixTransactionExecutor, MutationSelection
from panopticon.fix.https import HttpxTransport
from panopticon.fix.model import FixPlan
from panopticon.fix.plan import apply_bytes, unified_diff
from panopticon.fix.remediations import Remediation, plan_remediation
from panopticon.fix.service import execute
from panopticon.models.ids import JsonPointer
from panopticon.secrets import (
    KeyringSecretProvisioner,
    LinuxSecretServiceAdapter,
    MacOSKeychainAdapter,
    SecretStore,
    WindowsCredentialAdapter,
)
from panopticon.store.repository import ArtifactRepository
from panopticon.util.jsonc.document import SourceDocument
from panopticon.util.jsonc.parser import parse_document
from panopticon.util.jsonc.patch import JsoncPatchError, PatchOperation
from panopticon.util.jsonc.pointer import decode_pointer, value_at


@dataclass(frozen=True, slots=True)
class FixCommandResult:
    batch: FixBatchOutcome
    diffs: tuple[str, ...]
    exit_code: int


def _environment(home: Path | None = None) -> DiscoveryEnv:
    system = {"Darwin": "darwin", "Linux": "linux", "Windows": "windows"}.get(
        platform.system(),
        "linux",
    )
    return DiscoveryEnv(home or Path.home(), Path.cwd(), system, dict(os.environ))


def _secret_store() -> SecretStore:
    system = platform.system()
    if system == "Darwin":
        return MacOSKeychainAdapter()
    if system == "Windows":
        return WindowsCredentialAdapter()
    return LinuxSecretServiceAdapter()


def _recheck(selection: MutationSelection, plan: FixPlan) -> bool:
    try:
        current = parse_document(
            selection.config_path.read_bytes(),
            path=selection.config_path,
            logical_path=plan.logical_target,
        )
        actual = value_at(current.value, decode_pointer(selection.pointer))
    except JsoncPatchError:
        # A valid document with a missing pointer is the expected post-state
        # for removals.  Read/parse failures are not evidence of resolution:
        # treating a deleted or concurrently-corrupted file as resolved would
        # incorrectly commit the transaction.
        return plan.patches[0].operation is PatchOperation.REMOVE
    except ValueError:
        return False
    except OSError:
        return False
    # Re-evaluate the originating CFG condition at the mutated pointer rather
    # than treating a successful byte replacement as proof of resolution.
    # This keeps the transaction boundary independent of discovery adapters
    # while still rejecting a patch that leaves its finding active.
    if selection.fix_id == "FIX-001":
        return (
            isinstance(actual, str)
            and re.fullmatch(r"\$\{[A-Z][A-Z0-9_]{1,63}\}", actual) is not None
        )
    if selection.fix_id in {"FIX-002", "FIX-005"}:
        return actual == plan.patches[0].value and isinstance(actual, str) and "@" in actual
    if selection.fix_id == "FIX-004":
        if not isinstance(actual, str):
            return False
        normalized = actual.replace("\\", "/").rstrip("/")
        return (
            bool(normalized)
            and normalized not in {"~", "/", "$HOME"}
            and not re.fullmatch(r"(?:[A-Za-z]:)?/", normalized)
        )
    if selection.fix_id == "FIX-008":
        return isinstance(actual, str) and actual.startswith("https://")
    return actual == plan.patches[0].value


def _undo_selection(request: FixCommandRequest, env: DiscoveryEnv) -> FixSelection:
    transaction_id = request.undo or ""
    if re.fullmatch(r"[0-9a-f]{20}", transaction_id) is None:
        raise ValueError("INVALID_TRANSACTION_ID")
    repository = ArtifactRepository(env.home / ".panopticon")
    path = repository.root / "fix" / "journal" / f"{transaction_id}.json"
    journal = FixJournal.model_validate_json(path.read_bytes())
    logical = str(journal.config_path)
    target = env.home / logical[2:] if logical.startswith("~/") else Path(logical)
    return FixSelection(
        journal.fix_id,
        target,
        JsonPointer(""),
        value=transaction_id,
    )


def _planned(
    selections: tuple[FixSelection, ...],
    documents: Mapping[Path, SourceDocument],
    store: SecretStore,
    *,
    offline: bool,
) -> tuple[Remediation, ...]:
    remediations: list[Remediation] = []
    for selection in selections:
        document = documents[selection.config_path]
        remediations.append(
            plan_remediation(
                selection,
                document,
                secure_store=store,
                https_transport=None if offline else HttpxTransport(),
            )
        )
    return tuple(remediations)


def run_fix(request: FixCommandRequest, *, env: DiscoveryEnv | None = None) -> FixCommandResult:
    active_env = env or _environment()
    repository = ArtifactRepository(active_env.home / ".panopticon")
    store = _secret_store()
    executor = FixTransactionExecutor(
        repository,
        lambda: datetime.now(UTC),
        secret_store=store,
        secret_provisioner=KeyringSecretProvisioner(),
        rechecker=_recheck,
    )
    if request.undo is not None:
        try:
            selection = _undo_selection(request, active_env)
        except (OSError, ValueError):
            return FixCommandResult(FixBatchOutcome(()), (), 4)
        batch = execute(
            FixRequest((selection,), dry_run=False, undo=True),
            {},
            transaction=executor,
        )
        return FixCommandResult(batch, (), 0 if batch.writes else 4)
    matching = matching_entries(active_env, request)
    if not matching or request.rule is None:
        return FixCommandResult(FixBatchOutcome(()), (), 4)
    selected = matching
    try:
        selections = tuple(build_selection(entry, request) for entry in selected)
        documents = {
            entry.config_path: parse_document(
                entry.config_path.read_bytes(),
                path=entry.config_path,
                logical_path=entry.logical_path,
            )
            for entry in selected
        }
    except (OSError, ValueError, JsoncPatchError):
        return FixCommandResult(FixBatchOutcome(()), (), 4)
    remediations = _planned(selections, documents, store, offline=request.offline)
    planned = FixBatchOutcome(tuple(remediation.outcome for remediation in remediations))
    diffs = tuple(
        unified_diff(remediation.plan, apply_bytes(remediation.plan))
        for remediation in remediations
        if remediation.plan is not None
    )
    if request.dry_run or not request.yes:
        return FixCommandResult(planned, diffs, 0)
    outcomes = []
    for selection, remediation in zip(selections, remediations, strict=True):
        if remediation.plan is None:
            outcomes.append(remediation.outcome)
            continue
        receipt = executor.apply(remediation.plan, selection, recheck=True)
        outcomes.append(
            FixOutcome(
                selection.fix_id,
                receipt.status,
                receipt.reason_code,
                remediation.plan.patches,
                receipt.written_paths,
                receipt.transaction_id,
            )
        )
    applied = FixBatchOutcome(tuple(outcomes))
    success = all(
        outcome.status in {FixOutcomeStatus.APPLIED, FixOutcomeStatus.RECHECKED}
        for outcome in applied.outcomes
    )
    return FixCommandResult(applied, diffs, 0 if success else 4)


__all__ = ["FixCommandRequest", "FixCommandResult", "run_fix"]
