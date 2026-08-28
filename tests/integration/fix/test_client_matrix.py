from __future__ import annotations

import json
from pathlib import Path

import pytest

from panopticon.fix.cli_model import FixChoice, FixOutcomeStatus, FixRequest, FixSelection
from panopticon.fix.plan import apply_bytes
from panopticon.fix.service import TransactionReceipt, execute
from panopticon.models.ids import JsonPointer
from panopticon.util.jsonc.parser import parse_document

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


class RecordingTransaction:
    def __init__(self, *, conflict: bool = False) -> None:
        self.conflict = conflict
        self.applied = []
        self.undone = []

    def apply(self, plan, selection, *, recheck):
        self.applied.append((plan, selection, recheck))
        if self.conflict:
            return TransactionReceipt(FixOutcomeStatus.CONFLICT, "UNDO_CONFLICT")
        plan.target.write_bytes(apply_bytes(plan))
        return TransactionReceipt(
            FixOutcomeStatus.RECHECKED, "TRANSACTION_COMPLETE", (plan.target,), "a" * 20
        )

    def undo(self, selection):
        self.undone.append(selection)
        return TransactionReceipt(FixOutcomeStatus.UNDONE, "UNDO_COMPLETE", (), selection.value)


class GoodTransport:
    def request(self, method, url, headers, body=None):
        return 200, {}, b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2026-07-28"}}'


def _document(tmp_path: Path) -> tuple[Path, object, bytes]:
    fixture = json.loads(FIXTURE.read_text())
    source = b"// matrix comment\r\n" + json.dumps(fixture["config"], indent=2).encode() + b"\r\n"
    path = tmp_path / "config.json"
    path.write_bytes(source)
    return path, parse_document(source, path=path, logical_path="~/config.json"), source


@pytest.mark.parametrize("client", CLIENTS)
@pytest.mark.parametrize("fix_id", tuple(POINTERS))
def test_matrix_dry_run_and_apply_preserves_source_and_selects_only_target(
    client, fix_id, tmp_path
):
    fixture = json.loads(FIXTURE.read_text())
    applicable = client in fixture["applicable"][fix_id]
    path, document, original = _document(tmp_path)
    pointer, value, version = POINTERS[fix_id]
    selection = FixSelection(
        fix_id, path, JsonPointer(pointer), FixChoice.APPLY, value, version, client
    )
    transport = GoodTransport() if fix_id == "FIX-008" else None
    dry = execute(
        FixRequest((selection,), dry_run=True), {path: document}, https_transport=transport
    )
    expected = (
        FixOutcomeStatus.GUIDANCE
        if fix_id == "FIX-001"
        else (FixOutcomeStatus.PLANNED if applicable else FixOutcomeStatus.GUIDANCE)
    )
    assert dry.outcomes[0].status is expected
    assert path.read_bytes() == original
    if not applicable or fix_id == "FIX-001":
        return
    tx = RecordingTransaction()
    applied = execute(
        FixRequest((selection,), dry_run=False, recheck=True),
        {path: document},
        transaction=tx,
        https_transport=transport,
    )
    assert applied.outcomes[0].status is FixOutcomeStatus.RECHECKED
    assert b"matrix comment" in path.read_bytes() and b"remote.invalid" in path.read_bytes()
    assert b"keep-server@1.2.3" in path.read_bytes()
    assert tx.applied[0][2] is True


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
    tx = RecordingTransaction(conflict=True)
    result = execute(FixRequest((selection,), dry_run=False), {path: document}, transaction=tx)
    assert result.outcomes[0].status is FixOutcomeStatus.CONFLICT
