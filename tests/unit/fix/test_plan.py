"""Acceptance coverage for deterministic, syntax-preserving fix plans."""

from pathlib import Path

from panopticon.fix.model import FixPlan, FixPrompt
from panopticon.fix.plan import apply_bytes, make_plan, plan_hash, unified_diff
from panopticon.models.ids import ConfigPath, JsonPointer
from panopticon.util.jsonc.parser import parse_document
from panopticon.util.jsonc.patch import JsoncPatch, PatchOperation


def test_plain_and_encrypted_fix_undo_exact_bytes() -> None:
    original = (
        b"// keep this comment\r\n"
        b'{\r\n  "token": "raw-token-value",\r\n'
        b'  "keep": 7, // unknown key\r\n  "name": "caf\xc3\xa9"\r\n}\r\n'
    )
    target = Path("config.jsonc")
    document = parse_document(original, path=target, logical_path=ConfigPath("~/config.jsonc"))
    patch = JsoncPatch(PatchOperation.REPLACE, JsonPointer("/name"), "updated")
    plan = make_plan(target, document, (patch,), (FixPrompt("confirm"),), mode=0o600)

    assert isinstance(plan, FixPlan)
    assert plan.original == original
    assert plan.original_hash == plan.original_hash
    assert plan.mode == 0o600
    updated = apply_bytes(plan)
    assert updated == (
        b"// keep this comment\r\n"
        b'{\r\n  "token": "raw-token-value",\r\n'
        b'  "keep": 7, // unknown key\r\n  "name": "updated"\r\n}\r\n'
    )
    assert plan_hash(plan) == plan_hash(plan)
    rendered = unified_diff(plan, updated)
    assert rendered == unified_diff(plan, updated)
    assert "raw-token-value" not in rendered
    assert "<redacted>" in rendered
    assert repr(plan).find("raw-token-value") < 0

    # The byte payload is suitable for an encrypted backup boundary and remains opaque in repr.
    from panopticon.fix.backup import encrypted_backup_request
    from panopticon.fix.model import BackupRequest
    from panopticon.util.leak_check import LeakContext

    backup = encrypted_backup_request(
        BackupRequest(target, plan.logical_target, original, "fix", plan.original_hash),
        LeakContext(secrets=("raw-token-value",)),
    )
    assert backup.metadata.config_digest == plan.original_hash
    assert backup.metadata.source == "fix"
    assert "raw-token-value" not in repr(backup)
    assert "raw-token-value" not in repr(
        BackupRequest(target, plan.logical_target, original, "fix", plan.original_hash)
    )
