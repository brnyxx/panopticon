"""Install orchestration over discovery and the existing transaction boundary."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from panopticon.discovery import discover, registered_adapters
from panopticon.discovery.base import DiscoveryEnv, DiscoveryStatus
from panopticon.fix.executor import MutationSelection
from panopticon.fix.model import FixPlan
from panopticon.fix.service import TransactionReceipt
from panopticon.util.jsonc.parser import JsoncParseError, parse_document

from .model import (
    InstallAction,
    InstallBatchOutcome,
    InstallOutcome,
    InstallRequest,
    InstallStatus,
)
from .plan import plan_entry


class InstallTransaction(Protocol):
    def apply(
        self,
        plan: FixPlan,
        selection: MutationSelection,
        *,
        recheck: bool,
    ) -> TransactionReceipt: ...

    def preview_restore(self, transaction_id: str, plan: FixPlan) -> FixPlan | None: ...

    def restore_transaction(
        self,
        transaction_id: str,
        selection: MutationSelection,
    ) -> TransactionReceipt: ...


def _status(receipt: TransactionReceipt) -> InstallStatus:
    try:
        return InstallStatus(receipt.status.value)
    except ValueError:
        return InstallStatus.FAILED


def execute(
    request: InstallRequest,
    env: DiscoveryEnv,
    *,
    transaction: InstallTransaction | None = None,
) -> InstallBatchOutcome:
    adapter = next(
        (
            item
            for item in registered_adapters(env, generic_config=request.config_path)
            if item.name == request.client
        ),
        None,
    )
    if adapter is None:
        return InstallBatchOutcome((InstallOutcome("", InstallStatus.GUIDANCE, "UNKNOWN_CLIENT"),))
    entries = [
        entry
        for _path, result in discover(adapter, env)
        if result.status is DiscoveryStatus.FOUND
        for entry in result.entries
    ]
    entries.sort(key=lambda entry: (str(entry.config_path), str(entry.json_pointer), entry.name))
    if request.action is InstallAction.UNINSTALL:
        entries.reverse()
    outcomes: list[InstallOutcome] = []
    for entry in entries:
        if request.only is not None and entry.name != request.only:
            continue
        try:
            document = parse_document(
                entry.config_path.read_bytes(),
                path=entry.config_path,
                logical_path=entry.logical_path,
            )
            plan = plan_entry(
                entry,
                document,
                client=request.client,
                home=env.home,
                pano_command=request.pano_command,
                action=request.action,
            )
            if (
                request.action is InstallAction.UNINSTALL
                and plan.selection.value is not None
                and transaction is not None
            ):
                restore_plan = transaction.preview_restore(
                    plan.selection.value,
                    plan.fix_plan,
                )
                if restore_plan is None:
                    outcomes.append(
                        InstallOutcome(
                            entry.name,
                            InstallStatus.CONFLICT,
                            "RESTORE_PREVIEW_UNAVAILABLE",
                            plan,
                        )
                    )
                    continue
                plan = replace(plan, fix_plan=restore_plan)
        except JsoncParseError as error:
            outcomes.append(InstallOutcome(entry.name, InstallStatus.GUIDANCE, error.code))
            continue
        except OSError:
            outcomes.append(
                InstallOutcome(entry.name, InstallStatus.GUIDANCE, "CONFIG_READ_FAILED")
            )
            continue
        except ValueError as error:
            outcomes.append(InstallOutcome(entry.name, InstallStatus.GUIDANCE, str(error)))
            continue
        if request.dry_run or not request.yes:
            outcomes.append(
                InstallOutcome(
                    entry.name,
                    InstallStatus.PLANNED,
                    plan.reason_code,
                    plan,
                )
            )
            continue
        if transaction is None:
            outcomes.append(
                InstallOutcome(
                    entry.name,
                    InstallStatus.GUIDANCE,
                    "TRANSACTION_PORT_UNAVAILABLE",
                    plan,
                )
            )
            continue
        if request.action is InstallAction.UNINSTALL and plan.selection.value is not None:
            receipt = transaction.restore_transaction(
                plan.selection.value,
                plan.selection,
            )
        else:
            receipt = transaction.apply(plan.fix_plan, plan.selection, recheck=True)
        outcomes.append(
            InstallOutcome(
                entry.name,
                _status(receipt),
                receipt.reason_code,
                plan,
                receipt.transaction_id,
            )
        )
    return InstallBatchOutcome(tuple(outcomes))


__all__ = ["InstallTransaction", "execute"]
