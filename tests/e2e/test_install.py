from pathlib import Path

import pytest

from panopticon.discovery.base import DiscoveryEnv
from panopticon.discovery.generic import GenericAdapter
from panopticon.fix.cli_model import FixOutcomeStatus
from panopticon.fix.service import TransactionReceipt
from panopticon.install import service
from panopticon.install.model import InstallAction, InstallRequest, InstallStatus


class RecordingTransaction:
    def __init__(self) -> None:
        self.calls = []

    def apply(self, plan, selection, *, recheck: bool):
        self.calls.append((plan, selection, recheck))
        return TransactionReceipt(
            FixOutcomeStatus.RECHECKED, "TRANSACTION_COMPLETE", transaction_id="tx-1"
        )


def _env(tmp_path: Path) -> DiscoveryEnv:
    return DiscoveryEnv(tmp_path, tmp_path, "linux", {})


def test_install_launch_uninstall_restores_original_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "client.jsonc"
    original = (
        b'{\n  // preserved\n  "mcpServers": '
        b'{"demo": {"command": "node", "args": ["server.js"]}}\n}\n'
    )
    config.write_bytes(original)
    monkeypatch.setattr(service, "registered_adapters", lambda env: (GenericAdapter(config, env),))
    tx = RecordingTransaction()
    request = InstallRequest("generic", dry_run=True, pano_command="/usr/bin/python3")
    planned = service.execute(request, _env(tmp_path), transaction=tx)
    assert planned.successful and planned.outcomes[0].status is InstallStatus.PLANNED
    assert config.read_bytes() == original and tx.calls == []
    # Applying is delegated to the injected transaction and rechecked exactly once.
    applied = service.execute(
        request.__class__("generic", dry_run=False, yes=True, pano_command="/usr/bin/python3"),
        _env(tmp_path),
        transaction=tx,
    )
    assert applied.outcomes[0].status is InstallStatus.RECHECKED
    assert tx.calls and tx.calls[0][2] is True
    assert tx.calls[0][0].original_hash
    # The generated uninstall plan carries the recorded command/argv and removes metadata.
    config.write_bytes(
        b'{"mcpServers":{"demo":{"command":"shim","args":["wrap"],"_pano_original":{"v":1,"command":"node","args":["server.js"]}}}}'
    )
    uninstall = service.execute(
        InstallRequest("generic", action=InstallAction.UNINSTALL, pano_command="/usr/bin/python3"),
        _env(tmp_path),
        transaction=tx,
    )
    assert uninstall.outcomes[0].status is InstallStatus.PLANNED


def test_wrapped_remote_and_concurrent_entries_have_no_collateral_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "client.json"
    original = b'{"mcpServers":{"local":{"command":"node","args":["a"]},"remote":{"url":"https://example.test"},"disabled":{"command":"node","args":[],"disabled":true}}}'
    config.write_bytes(original)
    monkeypatch.setattr(service, "registered_adapters", lambda env: (GenericAdapter(config, env),))
    tx = RecordingTransaction()
    planned = service.execute(
        InstallRequest("generic", only="local", pano_command="/usr/bin/python3"),
        _env(tmp_path),
        transaction=tx,
    )
    assert len(planned.outcomes) == 1 and planned.outcomes[0].server_name == "local"
    assert config.read_bytes() == original
    # A concurrent edit is detected by the transaction boundary; no other entries are selected.
    config.write_bytes(original.replace(b'"a"', b'"edited"'))
    applied = service.execute(
        InstallRequest(
            "generic", only="local", dry_run=False, yes=True, pano_command="/usr/bin/python3"
        ),
        _env(tmp_path),
        transaction=tx,
    )
    assert len(applied.outcomes) == 1 and len(tx.calls) == 1
    assert config.read_bytes() != original
    remote = service.execute(
        InstallRequest("generic", only="remote", pano_command="/usr/bin/python3"),
        _env(tmp_path),
        transaction=tx,
    )
    assert remote.outcomes[0].reason_code == "REMOTE_NOT_TARGET"
    disabled = service.execute(
        InstallRequest("generic", only="disabled", pano_command="/usr/bin/python3"),
        _env(tmp_path),
        transaction=tx,
    )
    assert disabled.outcomes[0].reason_code == "DISABLED"
