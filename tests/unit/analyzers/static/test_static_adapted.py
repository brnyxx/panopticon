from __future__ import annotations

# Adapted static analyzer behavior.
from pathlib import Path

import pytest

from panopticon.analyzers.static.engine import run_static_scan
from panopticon.analyzers.static.model import ScannerConfig, StaticConfiguration
from panopticon.analyzers.static.traversal import collect_static_files


def test_static_scan_detects_untyped_tool_input_deterministically(tmp_path: Path) -> None:
    (tmp_path / "server.py").write_text(
        "@mcp.tool()\ndef search(query):\n    return query\n",
        encoding="utf-8",
    )
    configuration = StaticConfiguration(
        tmp_path,
        ScannerConfig(selected_rule_ids=("SENT-003",)),
    )

    first = run_static_scan(configuration)
    second = run_static_scan(configuration)

    assert [(match.rule_id, match.path, match.match_kinds) for match in first.matches] == [
        ("SENT-003", "server.py", ("untyped-parameter",))
    ]
    assert first.matches == second.matches
    assert first.summary.total_matches == 1


def test_traversal_skips_symlinks_and_rejects_malformed_source(tmp_path: Path) -> None:
    target = tmp_path / "target.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "linked.py").symlink_to(target)

    files = collect_static_files(tmp_path, ())

    assert [item.relative_path for item in files.python_files] == ["target.py"]
    assert files.warnings[0].code == "static_symlinks_skipped"

    target.write_text("def broken(:\n", encoding="utf-8")
    with pytest.raises(ValueError):
        collect_static_files(tmp_path, ())
