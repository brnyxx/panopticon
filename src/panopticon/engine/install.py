"""Engine entry points for reversible client installation."""

from __future__ import annotations

from panopticon.discovery.base import DiscoveryEnv
from panopticon.install.model import InstallBatchOutcome, InstallRequest
from panopticon.install.service import InstallTransaction, execute


def run_install(
    request: InstallRequest, env: DiscoveryEnv, *, transaction: InstallTransaction | None = None
) -> InstallBatchOutcome:
    return execute(request, env, transaction=transaction)


def run_uninstall(
    request: InstallRequest, env: DiscoveryEnv, *, transaction: InstallTransaction | None = None
) -> InstallBatchOutcome:
    if request.action.value != "uninstall":
        request = InstallRequest(
            request.client,
            action=type(request.action).UNINSTALL,
            only=request.only,
            dry_run=request.dry_run,
            yes=request.yes,
            pano_command=request.pano_command,
        )
    return execute(request, env, transaction=transaction)


__all__ = ["run_install", "run_uninstall"]
