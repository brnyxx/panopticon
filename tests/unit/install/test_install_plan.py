import hashlib
import sys
from pathlib import Path

import pytest

from panopticon.discovery._config import read_entries
from panopticon.install.model import InstallAction
from panopticon.install.plan import plan_entry
from panopticon.models import ConfigScope
from panopticon.util.jsonc.parser import parse_document


def _entry(tmp_path: Path, raw: str):
    path = tmp_path / "config.jsonc"
    path.write_bytes(raw.encode())
    result = read_entries(
        path, home=tmp_path, scope=ConfigScope.GLOBAL, pointers=("/mcpServers", "/servers")
    )
    assert result.entries
    return path, result.entries[0]


def test_install_plan_preserves_exact_source_metadata_and_wrapper_contract(tmp_path: Path) -> None:
    source = (
        '{\r\n  // keep this comment\r\n  "mcpServers": '
        '{"demo": {"command": "node", "args": ["server.js"]}}\r\n}\r\n'
    )
    path, entry = _entry(tmp_path, source)
    mode = 0o640
    path.chmod(mode)
    before = path.read_bytes()
    document = parse_document(before, path=path, logical_path=entry.logical_path)
    plan = plan_entry(
        entry,
        document,
        client="generic",
        home=tmp_path,
        pano_command=sys.executable,
        action=InstallAction.INSTALL,
    )
    assert plan.reason_code == "INSTALL_PLANNED"
    assert plan.patches[0].value == sys.executable
    wrapped = plan.patches[1].value
    assert wrapped[:1] == ["wrap"]
    assert wrapped[1] == "--server-id" and wrapped[3] == "--installation-id"
    assert wrapped[5:] == ["--", "node", "server.js"]
    assert hashlib.sha256(before).hexdigest() == document.original_sha256
    assert document.newline == "\r\n"
    assert path.stat().st_mode & 0o777 == mode


@pytest.mark.parametrize(
    "raw",
    [
        '{"mcpServers":{"a":{"command":"python","args":["x"],"disabled":true}}}',
        '{"mcpServers":{"a":{"command":"python","args":["x"],"enabled":false}}}',
        '{"mcpServers":{"a":{"url":"https://example.test"}}}',
        '{"mcpServers":{"a":{"transport":"sse","url":"https://example.test"}}}',
    ],
)
def test_install_plan_rejects_unsupported_disabled_and_remote_entries(
    tmp_path: Path, raw: str
) -> None:
    path, entry = _entry(tmp_path, raw)
    document = parse_document(path.read_bytes(), path=path, logical_path=entry.logical_path)
    with pytest.raises(ValueError) as error:
        plan_entry(
            entry,
            document,
            client="generic",
            home=tmp_path,
            pano_command=sys.executable,
            action=InstallAction.INSTALL,
        )
    assert str(error.value) in {"DISABLED", "REMOTE_NOT_TARGET", "UNSUPPORTED_STDIO"}


def test_install_plan_is_dry_run_and_uninstall_restores_original_command_args(
    tmp_path: Path,
) -> None:
    path, entry = _entry(
        tmp_path,
        '{"mcpServers":{"a":{"command":"node","args":["x"],"_pano_original":{"v":1,"command":"old","args":["a"]}}}}',
    )
    before = path.read_bytes()
    doc = parse_document(before, path=path, logical_path=entry.logical_path)
    plan = plan_entry(
        entry,
        doc,
        client="generic",
        home=tmp_path,
        pano_command=sys.executable,
        action=InstallAction.UNINSTALL,
    )
    assert path.read_bytes() == before
    assert [patch.value for patch in plan.patches[:2]] == ["old", ["a"]]
    assert plan.patches[2].operation.value == "REMOVE"


def test_uninstall_migrates_legacy_v0_metadata_and_rejects_duplicates(tmp_path: Path) -> None:
    path, entry = _entry(
        tmp_path,
        '{"mcpServers":{"a":{"command":"shim","args":["wrap"],"_pano_original":{"version":0,"original_command":"node","original_args":["x"]}}}}',
    )
    doc = parse_document(path.read_bytes(), path=path, logical_path=entry.logical_path)
    uninstall = plan_entry(
        entry,
        doc,
        client="generic",
        home=tmp_path,
        pano_command=sys.executable,
        action=InstallAction.UNINSTALL,
    )
    assert uninstall.patches[0].value == "node"
    assert uninstall.patches[1].value == ["x"]
    path2, entry2 = _entry(
        tmp_path, '{"mcpServers":{"a":{"command":"node","args":["wrap","--","node"]}}}'
    )
    doc2 = parse_document(path2.read_bytes(), path=path2, logical_path=entry2.logical_path)
    with pytest.raises(ValueError, match="ALREADY_WRAPPED"):
        plan_entry(
            entry2,
            doc2,
            client="generic",
            home=tmp_path,
            pano_command=sys.executable,
            action=InstallAction.INSTALL,
        )
