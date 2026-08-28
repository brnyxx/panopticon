"""Typed orchestration for remediation planning and transaction execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from panopticon.secrets.contracts import SecretStore
from panopticon.util.jsonc.document import SourceDocument

from .cli_model import (
    FixBatchOutcome,
    FixOutcome,
    FixOutcomeStatus,
    FixRequest,
    FixSelection,
)
from .https import HttpTransport
from .model import FixPlan
from .remediations import plan_remediation


@dataclass(frozen=True, slots=True)
class TransactionReceipt:
    status: FixOutcomeStatus
    reason_code: str
    written_paths: tuple[Path, ...] = ()
    transaction_id: str | None = None


class TransactionPort(Protocol):
    def apply(
        self,
        plan: FixPlan,
        selection: FixSelection,
        *,
        recheck: bool,
    ) -> TransactionReceipt: ...

    def undo(self, selection: FixSelection) -> TransactionReceipt: ...


def _unavailable(selection: FixSelection) -> FixOutcome:
    return FixOutcome(
        selection.fix_id,
        FixOutcomeStatus.GUIDANCE,
        "CONFIG_DOCUMENT_UNAVAILABLE",
    )


def execute(
    request: FixRequest,
    documents: Mapping[Path, SourceDocument],
    *,
    transaction: TransactionPort | None = None,
    secure_store: SecretStore | None = None,
    https_transport: HttpTransport | None = None,
) -> FixBatchOutcome:
    outcomes: list[FixOutcome] = []
    for selection in request.selections:
        if request.undo:
            if transaction is None:
                outcomes.append(
                    FixOutcome(
                        selection.fix_id,
                        FixOutcomeStatus.GUIDANCE,
                        "UNDO_JOURNAL_UNAVAILABLE",
                    )
                )
                continue
            receipt = transaction.undo(selection)
            outcomes.append(
                FixOutcome(
                    selection.fix_id,
                    receipt.status,
                    receipt.reason_code,
                    written_paths=receipt.written_paths,
                    transaction_id=receipt.transaction_id,
                )
            )
            continue
        document = documents.get(selection.config_path)
        if document is None:
            outcomes.append(_unavailable(selection))
            continue
        remediation = plan_remediation(
            selection,
            document,
            secure_store=secure_store,
            https_transport=https_transport,
        )
        if remediation.plan is None:
            outcomes.append(remediation.outcome)
            continue
        if request.dry_run:
            outcomes.append(remediation.outcome)
            continue
        if transaction is None:
            outcomes.append(
                FixOutcome(
                    selection.fix_id,
                    FixOutcomeStatus.GUIDANCE,
                    "TRANSACTION_PORT_UNAVAILABLE",
                    remediation.plan.patches,
                )
            )
            continue
        receipt = transaction.apply(
            remediation.plan,
            selection,
            recheck=request.recheck,
        )
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
    return FixBatchOutcome(tuple(outcomes))


__all__ = ["TransactionPort", "TransactionReceipt", "execute"]
