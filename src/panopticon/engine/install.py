"""Engine entry points for reversible client installation."""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from panopticon.discovery.base import DiscoveryEnv
from panopticon.fix.executor import FixTransactionExecutor, MutationSelection
from panopticon.fix.model import FixPlan
from panopticon.install.model import (
    InstallAction,
    InstallBatchOutcome,
    InstallRequest,
)
from panopticon.install.service import InstallTransaction, execute
from panopticon.secrets import (
    LinuxSecretServiceAdapter,
    MacOSKeychainAdapter,
    SecretStore,
    WindowsCredentialAdapter,
)
from panopticon.store.repository import ArtifactRepository
from panopticon.util.jsonc.parser import parse_document
from panopticon.util.jsonc.patch import JsoncPatchError
from panopticon.util.jsonc.pointer import decode_pointer, value_at


def _environment() -> DiscoveryEnv:
    system = {"Darwin": "darwin", "Linux": "linux", "Windows": "windows"}.get(
        platform.system(),
        "linux",
    )
    return DiscoveryEnv(Path.home(), Path.cwd(), system, dict(os.environ))


def _store() -> SecretStore:
    if platform.system() == "Darwin":
        return MacOSKeychainAdapter()
    if platform.system() == "Windows":
        return WindowsCredentialAdapter()
    return LinuxSecretServiceAdapter()


def recheck_install(selection: MutationSelection, plan: FixPlan) -> bool:
    try:
        document = parse_document(
            selection.config_path.read_bytes(),
            path=selection.config_path,
            logical_path=plan.logical_target,
        )
        value = value_at(document.value, decode_pointer(selection.pointer))
    except (OSError, JsoncPatchError):
        return False
    if not isinstance(value, dict):
        return False
    if selection.fix_id == "INSTALL":
        metadata = value.get("_pano_original")
        args = value.get("args")
        return (
            isinstance(metadata, dict)
            and metadata.get("v") == 1
            and isinstance(args, list)
            and bool(args)
            and args[0] == "wrap"
        )
    return "_pano_original" not in value


def _transaction(env: DiscoveryEnv) -> FixTransactionExecutor:
    return FixTransactionExecutor(
        ArtifactRepository(env.home / ".panopticon"),
        lambda: datetime.now(UTC),
        secret_store=_store(),
        rechecker=recheck_install,
    )


def _resolved_request(request: InstallRequest) -> InstallRequest:
    command = request.pano_command or shutil.which("pano")
    return replace(request, pano_command=command)


def run_install(
    request: InstallRequest,
    env: DiscoveryEnv | None = None,
    *,
    transaction: InstallTransaction | None = None,
) -> InstallBatchOutcome:
    active_env = env or _environment()
    active_transaction = transaction or _transaction(active_env)
    return execute(
        _resolved_request(request),
        active_env,
        transaction=active_transaction,
    )


def run_uninstall(
    request: InstallRequest,
    env: DiscoveryEnv | None = None,
    *,
    transaction: InstallTransaction | None = None,
) -> InstallBatchOutcome:
    active = replace(request, action=InstallAction.UNINSTALL)
    return run_install(active, env, transaction=transaction)


__all__ = [
    "InstallAction",
    "InstallRequest",
    "recheck_install",
    "run_install",
    "run_uninstall",
]
