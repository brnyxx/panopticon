from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from panopticon.analyzers.static import semgrep_adapter as adapter
from panopticon.analyzers.static.model import ParsedPythonFile, StaticFileSet


def _files(tmp_path: Path) -> StaticFileSet:
    path = tmp_path / "server.py"
    source = "x = 1\n"
    path.write_text(source, encoding="utf-8")
    parsed = ParsedPythonFile(path, "server.py", source, ast.parse(source))
    return StaticFileSet((parsed,), (), 1, 0, ())


def test_run_semgrep_filters_rules_and_requires_pinned_version(monkeypatch, tmp_path: Path) -> None:
    files = _files(tmp_path)
    assert adapter.run_semgrep(files, ("SENT-001",), tmp_path, deadline=999) == {}
    monkeypatch.setattr(adapter, "version", lambda _: "1.169.0")
    with pytest.raises(adapter.SemgrepExecutionError, match="version mismatch"):
        adapter.run_semgrep(files, ("SENT-002",), tmp_path, deadline=999)
    monkeypatch.setattr(adapter, "version", lambda _: adapter.SEMGREP_VERSION)
    monkeypatch.setattr(adapter.shutil, "which", lambda _: None)
    monkeypatch.setattr(adapter.sys, "executable", str(tmp_path / "python"))
    with pytest.raises(adapter.SemgrepExecutionError, match="not available"):
        adapter.run_semgrep(files, ("SENT-002",), tmp_path, deadline=adapter.time.monotonic() + 10)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("not-json", "invalid JSON"),
        ("{}", "unexpected JSON shape"),
        ('{"results": [], "errors": ["x"]}', "scan errors"),
    ],
)
def test_semgrep_parse_errors(raw: str, message: str) -> None:
    with pytest.raises(adapter.SemgrepExecutionError, match=message):
        adapter._parse(raw)


def test_semgrep_collect_valid_result_and_out_of_scope(tmp_path: Path) -> None:
    files = _files(tmp_path)
    results = {"SENT-002": []}
    payload = {
        "results": [
            {
                "check_id": "x",
                "path": str(tmp_path / "server.py"),
                "start": {"line": 2, "col": 1},
                "end": {"line": 2, "col": 1},
                "extra": {"metadata": {"sentinel_rule_id": "SENT-002"}, "lines": "hit"},
            }
        ]
    }
    adapter._collect(payload, results, files, tmp_path)
    match = results["SENT-002"][0]
    assert match.path == "server.py" and match.range.end_column == 2 and match.snippet == "hit"
    with pytest.raises(adapter.SemgrepExecutionError, match="out-of-scope"):
        adapter._collect(
            {
                "results": [
                    {
                        "extra": {"metadata": {"sentinel_rule_id": "SENT-002"}},
                        "start": {"line": 1, "col": 1},
                        "end": {"line": 1, "col": 2},
                        "path": str(tmp_path / "other.py"),
                    }
                ]
            },
            results,
            files,
            tmp_path,
        )


@pytest.mark.asyncio
async def test_run_batches_uses_injected_async_subprocess(monkeypatch, tmp_path: Path) -> None:
    files = _files(tmp_path)

    class Proc:
        returncode = 0

        async def communicate(self):
            return (json.dumps({"results": []}).encode(), b"")

    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append(args)
        return Proc()

    monkeypatch.setattr(adapter.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(adapter.time, "monotonic", lambda: 0.0)
    results = await adapter._run_batches(
        "semgrep",
        [tmp_path / "r.yaml"],
        [tmp_path / "server.py"],
        files,
        {"SENT-002": []},
        tmp_path,
        10.0,
    )
    assert results == {"SENT-002": []}
    assert calls and calls[0][0:3] == ("semgrep", "scan", "--json")


@pytest.mark.asyncio
async def test_run_batches_converts_subprocess_failures_and_deadline(
    monkeypatch, tmp_path: Path
) -> None:
    files = _files(tmp_path)

    async def failing(*args, **kwargs):
        raise OSError("missing")

    monkeypatch.setattr(adapter.asyncio, "create_subprocess_exec", failing)
    with pytest.raises(adapter.SemgrepExecutionError, match="execution failed"):
        await adapter._run_batches(
            "semgrep",
            [],
            [tmp_path / "server.py"],
            files,
            {"SENT-002": []},
            tmp_path,
            adapter.time.monotonic() + 10,
        )
    monkeypatch.setattr(adapter.time, "monotonic", lambda: 100.0)
    with pytest.raises(adapter.SemgrepExecutionError, match="exceeded"):
        await adapter._run_batches(
            "semgrep", [], [tmp_path / "server.py"], files, {"SENT-002": []}, tmp_path, 0.0
        )
