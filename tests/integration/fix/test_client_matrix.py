from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from panopticon.engine.fix import _recheck
from panopticon.fix.cli_model import FixChoice, FixOutcomeStatus, FixRequest, FixSelection
from panopticon.fix.executor import FixTransactionExecutor
from panopticon.fix.service import execute
from panopticon.models.ids import JsonPointer
from panopticon.secrets import InMemorySecretStore
from panopticon.store.repository import ArtifactRepository
from panopticon.util.jsonc.parser import parse_document
from panopticon.util.leak_check import LeakContext

FIXTURE = Path(__file__).parents[2] / "fixtures" / "fix" / "client_matrix.json"
CLIENTS = ("claude-desktop", "claude-code", "cursor", "vscode", "windsurf", "generic")
POINTERS = {
    "FIX-001": ("/mcpServers/target/env/PANO_SYNTHETIC_TOKEN", None, None),
    "FIX-002": ("/mcpServers/target/args/0", None, "1.2.3"),
    "FIX-004": ("/mcpServers/target/args/2", "/safe/config", None),
    "FIX-005": ("/mcpServers/target/args/0", None, "2.0.0"),
    "FIX-008": ("/mcpServers/target/url", None, None),
    "FIX-010": ("/mcpServers/target", None, None),
}


class GoodTransport:
    def request(self, method, url, headers, body=None):
        return 200, {}, b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2026-07-28"}}'


def _document(tmp_path: Path) -> tuple[Path, object, bytes]:
    fixture = json.loads(FIXTURE.read_text())
    source = b"// matrix comment\r\n" + json.dumps(fixture["config"], indent=2).encode() + b"\r\n"
    path = tmp_path / "config.json"
    path.write_bytes(source)
    return path, parse_document(source, path=path, logical_path="~/config.json"), source


def _executor(tmp_path: Path, store: InMemorySecretStore | None = None) -> FixTransactionExecutor:
    context = LeakContext(secrets=("synthetic-token-value", "synthetic-header-value"))

    class Provisioner:
        def provision(self, key: str, value: str) -> bool:
            return bool(key and value)

    return FixTransactionExecutor(
        ArtifactRepository(tmp_path / "state", context),
        lambda: datetime(2026, 8, 29, tzinfo=UTC),
        secret_store=store or InMemorySecretStore(),
        secret_provisioner=Provisioner(),
        rechecker=_recheck,
    )


@pytest.mark.parametrize("client", CLIENTS)
@pytest.mark.parametrize("fix_id", tuple(POINTERS))
def test_matrix_dry_run_and_apply_preserves_source_and_selects_only_target(
    client, fix_id, tmp_path
):
    fixture = json.loads(FIXTURE.read_text())
    applicable = client in fixture["applicable"][fix_id]
    path, document, original = _document(tmp_path)
    pointer, value, version = POINTERS[fix_id]
    selection_value = value or ("PANO_SYNTHETIC_TOKEN" if fix_id == "FIX-001" else None)
    selection = FixSelection(
        fix_id, path, JsonPointer(pointer), FixChoice.APPLY, selection_value, version, client
    )
    transport = GoodTransport() if fix_id == "FIX-008" else None
    store = InMemorySecretStore()
    dry = execute(
        FixRequest((selection,), dry_run=True),
        {path: document},
        secure_store=store,
        https_transport=transport,
    )
    expected = (
        FixOutcomeStatus.PLANNED
        if applicable and not (fix_id == "FIX-001" and client == "claude-desktop")
        else FixOutcomeStatus.GUIDANCE
    )
    assert dry.outcomes[0].status is expected
    assert path.read_bytes() == original
    if not applicable or (fix_id == "FIX-001" and client == "claude-desktop"):
        return
    tx = _executor(tmp_path, store)
    applied = execute(
        FixRequest((selection,), dry_run=False, recheck=True),
        {path: document},
        transaction=tx,
        secure_store=store,
        https_transport=transport,
    )
    assert applied.outcomes[0].status is FixOutcomeStatus.RECHECKED
    changed = path.read_bytes()
    assert changed != original
    assert b"matrix comment" in changed
    assert hashlib.sha256(changed).hexdigest() != hashlib.sha256(original).hexdigest()
    for artifact in applied.outcomes[0].written_paths[1:]:
        if artifact.exists():
            persisted = artifact.read_bytes()
            assert b"synthetic-token-value" not in persisted
            assert b"synthetic-header-value" not in persisted
    journal = applied.outcomes[0].written_paths[-1]
    assert json.loads(journal.read_bytes())["status"] == "RECHECKED"
    transaction_id = applied.outcomes[0].transaction_id
    assert transaction_id is not None
    undone = execute(
        FixRequest(
            (FixSelection(fix_id, path, JsonPointer(""), value=transaction_id, client=client),),
            dry_run=False,
            undo=True,
        ),
        {},
        transaction=tx,
    )
    assert undone.outcomes[0].status is FixOutcomeStatus.UNDONE
    assert path.read_bytes() == original
    assert json.loads(journal.read_bytes())["status"] == "UNDONE"


def test_secret_fixes_are_guidance_only_without_secure_store(tmp_path):
    path, document, original = _document(tmp_path)
    selection = FixSelection(
        "FIX-001",
        path,
        JsonPointer(POINTERS["FIX-001"][0]),
        value="PANO_SYNTHETIC_TOKEN",
        client="cursor",
    )
    result = execute(FixRequest((selection,), dry_run=False), {path: document})
    assert result.outcomes[0].status is FixOutcomeStatus.GUIDANCE
    assert result.outcomes[0].reason_code == "SECURE_STORE_UNAVAILABLE"
    assert path.read_bytes() == original


def test_concurrent_edit_is_rejected(tmp_path):
    path, document, _ = _document(tmp_path)
    selection = FixSelection(
        "FIX-002", path, JsonPointer(POINTERS["FIX-002"][0]), version="1.2.3", client="generic"
    )
    tx = _executor(tmp_path)
    path.write_bytes(b'{"concurrent": true}\n')
    result = execute(FixRequest((selection,), dry_run=False), {path: document}, transaction=tx)
    assert result.outcomes[0].status is FixOutcomeStatus.CONFLICT
