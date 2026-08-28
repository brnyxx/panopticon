"""Install orchestration over discovery and the existing transaction boundary."""

from __future__ import annotations

from typing import Protocol

from panopticon.discovery import discover, registered_adapters
from panopticon.discovery.base import DiscoveryEnv, RawServerEntry

from .model import InstallAction, InstallBatchOutcome, InstallOutcome, InstallRequest
from .plan import plan_entry


class InstallTransaction(Protocol):
    def apply(self, plan: object, *, yes: bool = False) -> object: ...
    def undo(self, plan: object) -> object: ...


def execute(
    request: InstallRequest, env: DiscoveryEnv, *, transaction: InstallTransaction | None = None
) -> InstallBatchOutcome:
    adapters = registered_adapters(env)
    adapter = next((a for a in adapters if a.name == request.client), None)
    if adapter is None:
        return InstallBatchOutcome((InstallOutcome("", "GUIDANCE", "UNKNOWN_CLIENT"),))
    entries: list[RawServerEntry] = []
    for _path, result in discover(adapter, env):
        if result.status.value == "FOUND":
            entries.extend(result.entries)
    entries.sort(key=lambda e: (str(e.config_path), str(e.json_pointer), e.name))
    outcomes: list[InstallOutcome] = []
    for entry in entries:
        if request.only and entry.name != request.only:
            continue
        try:
            plan = plan_entry(
                entry,
                pano_command=request.pano_command,
                uninstall=request.action is InstallAction.UNINSTALL,
            )
        except ValueError as error:
            outcomes.append(InstallOutcome(entry.name, "GUIDANCE", str(error)))
            continue
        if request.dry_run:
            outcomes.append(InstallOutcome(entry.name, "PLANNED", plan.reason_code, plan=plan))
            continue
        if transaction is None:
            outcomes.append(
                InstallOutcome(entry.name, "GUIDANCE", "TRANSACTION_PORT_UNAVAILABLE", plan=plan)
            )
            continue
        try:
            receipt = (
                transaction.apply(plan, yes=request.yes)
                if request.action is InstallAction.INSTALL
                else transaction.undo(plan)
            )
            status = getattr(receipt, "status", "APPLIED")
            reason = getattr(receipt, "reason_code", "INSTALL_APPLIED")
            txid = getattr(receipt, "transaction_id", None)
            outcomes.append(InstallOutcome(entry.name, str(status), str(reason), plan, txid))
        except (OSError, RuntimeError, ValueError):
            outcomes.append(InstallOutcome(entry.name, "FAILED", "TRANSACTION_FAILED", plan=plan))
    return InstallBatchOutcome(tuple(outcomes))


__all__ = ["InstallTransaction", "execute"]
