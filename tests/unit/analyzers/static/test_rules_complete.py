from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from panopticon.analyzers.static.ast_utils import (
    discover_prompt_functions,
    discover_tool_regions,
    import_aliases,
    lines_for_range,
    module_name,
    range_for_node,
    resolve_name,
)
from panopticon.analyzers.static.model import (
    ParsedPythonFile,
    RuleRunState,
    ScannerConfig,
    SecretAllowlistEntry,
    StaticConfiguration,
    StaticContext,
    StaticFileSet,
    StaticRuleOptions,
)
from panopticon.analyzers.static.rules import sent001, sent003, sent004, sent005, sent006, sent007
from panopticon.analyzers.static.traversal import collect_static_files


def _context(
    tmp_path: Path,
    source: str,
    *,
    options: StaticRuleOptions = StaticRuleOptions(),
    permissions=None,
):
    path = tmp_path / "server.py"
    path.write_text(source, encoding="utf-8")
    tree = ast.parse(source)
    parsed = ParsedPythonFile(path, "server.py", source, tree)
    config = StaticConfiguration(tmp_path, ScannerConfig(rule_options=options))
    if permissions is not None:
        config = SimpleNamespace(
            scan_root=tmp_path, scanner=config.scanner, permissions=permissions
        )
    return StaticContext(config, StaticFileSet((parsed,), (), 1, 0, ()))


def test_ast_utils_regions_aliases_ranges_and_module_names(tmp_path: Path) -> None:
    source = """import foo.bar as fb\nfrom typing import Any as Anything\n@mcp.tool(name='renamed')\ndef fn(x): return x\n@mcp.call_tool\ndef dispatch(name, arguments):\n    if name == 'echo': return arguments['x']\n@mcp.prompt\ndef prompt(): pass\n"""
    context = _context(tmp_path, source)
    file = context.files.python_files[0]
    regions = discover_tool_regions(file)
    assert [r.name for r in regions] == ["renamed", "echo"]
    assert len(discover_prompt_functions(file)) == 1
    aliases = import_aliases(file)
    assert aliases == {"fb": "foo.bar", "Anything": "typing.Any"}
    assert resolve_name("fb.run", aliases) == "foo.bar.run"
    node = file.tree.body[2].decorator_list[0]
    source_range = range_for_node(node)
    assert source_range.start_line == 3 and source_range.start_column == 2
    assert lines_for_range(source, source_range).startswith("@mcp.tool")
    assert module_name(tmp_path, file) == "server"


def test_sent001_detects_broad_usage_missing_manifest_and_justification(tmp_path: Path) -> None:
    source = (
        """@mcp.tool()\ndef read(x):\n    open(x, 'w')\n    requests.get('https://example.com')\n"""
    )
    permissions = SimpleNamespace(
        tools={
            "read": SimpleNamespace(
                filesystem=SimpleNamespace(
                    read=SimpleNamespace(scopes=(), broad_scope_justification=None),
                    write=SimpleNamespace(scopes=(), broad_scope_justification=None),
                ),
                network=SimpleNamespace(scopes=(), broad_scope_justification="approved"),
            )
        }
    )
    state = RuleRunState()
    sent001.detect(_context(tmp_path, source, permissions=permissions), state)
    assert [(m.match_kinds, m.range.start_line) for m in state.matches] == [
        (("broad-filesystem.write",), 3)
    ]
    assert state.exemptions == {"justified_network": 1}
    state = RuleRunState()
    sent001.detect(
        _context(
            tmp_path, "@mcp.tool()\ndef absent(): pass\n", permissions=SimpleNamespace(tools={})
        ),
        state,
    )
    assert state.matches[0].match_kinds == ("missing-tool-permissions",)


def test_sent003_validation_dispatch_and_typed_exemptions(tmp_path: Path) -> None:
    source = """@mcp.tool()
def unsafe(data): return data
@mcp.tool()
def safe(data: dict):
    Model.model_validate(data)
    return data
@mcp.call_tool
def dispatch(name, arguments):
    if name == 'x': return arguments.get('x')
"""
    state = RuleRunState()
    sent003.detect(_context(tmp_path, source), state)
    assert [m.match_kinds for m in state.matches] == [
        ("untyped-parameter",),
        ("unchecked-dispatch-arguments",),
    ]
    assert state.exemptions == {"validated_before_use": 1}


def test_sent004_prompt_taint_sink_and_sanitized_exemption(tmp_path: Path) -> None:
    source = """@mcp.prompt()\ndef bad():\n    value = tool.call_tool()\n    client.chat.completions.create(messages=value)\n@ mcp.prompt()\ndef clean():\n    value = tool.call_tool()\n    value = sanitize(value)\n    return value\n""".replace(
        "@ mcp", "@mcp"
    )
    state = RuleRunState()
    sent004.detect(
        _context(tmp_path, source, options=StaticRuleOptions(sanitizers=("server.sanitize",))),
        state,
    )
    assert [m.match_kinds for m in state.matches] == [("prompt-taint",)]
    assert state.exemptions == {"sanitizer_or_no_taint": 1}


def test_sent005_redacts_secret_and_honors_allowlist_and_reserved(tmp_path: Path) -> None:
    secret = "sk-" + "A" * 24
    source = f"API_KEY = '{secret}'\n"
    context = _context(tmp_path, source)
    candidate = sent005.StaticMatch("SENT-005", "server.py", sent005.SourceRange(1, 1, 1, 2), "")
    state = RuleRunState()
    sent005.run(context, [candidate], state)
    assert len(state.matches) == 1 and secret not in state.matches[0].snippet
    fingerprint = state.matches[0].fingerprint
    options = StaticRuleOptions(secret_allowlist=(SecretAllowlistEntry("server.py", fingerprint),))
    state = RuleRunState()
    sent005.run(_context(tmp_path, source, options=options), [candidate], state)
    assert state.matches == [] and state.exemptions == {"configured_path_and_fingerprint": 1}
    fixture = _context(tmp_path, f"TOKEN=sk-test-{'B' * 24}\n")
    state = RuleRunState()
    sent005.run(
        fixture,
        [candidate.__class__("SENT-005", "tests/fixtures/x.py", candidate.range, "")],
        state,
    )
    assert state.matches == []


def test_sent006_routes_public_verified_and_missing_auth(tmp_path: Path) -> None:
    source = """from fastapi import APIRouter, Depends\nrouter=APIRouter()\ndef auth(token):\n    jwt.decode(token, 'k'); raise ValueError()\n@router.get('/public')\ndef a(): pass\n@router.post('/private', dependencies=[Depends(auth)])\ndef b(): pass\n@router.get('/open')\ndef c(): pass\n"""
    options = StaticRuleOptions(public_routes=("GET public",))
    state = RuleRunState()
    sent006.detect(_context(tmp_path, source, options=options), state)
    assert [m.match_kinds for m in state.matches] == [("missing-auth",)]
    assert state.exemptions == {"configured_public_route": 1, "verified_auth": 1}


def test_sent007_manifest_verification_and_invalid_anchor(tmp_path: Path) -> None:
    source = """import json, hashlib\ndef load_manifest():\n    json.load(open('manifest.json'))\ndef verified_manifest():\n    hashlib.sha256(b'x')\n    json.loads('{}')\n"""
    (tmp_path / "sentinel.integrity.yaml").write_text(
        "version: 1\nmanifests: {}\n", encoding="utf-8"
    )
    state = RuleRunState()
    sent007.detect(_context(tmp_path, source), state)
    assert [m.match_kinds for m in state.matches] == [("unverified-manifest",)]
    (tmp_path / "sentinel.integrity.yaml").write_text(
        "version: 2\nmanifests: {}\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="invalid sentinel.integrity.yaml"):
        sent007.detect(_context(tmp_path, source), RuleRunState())


def test_traversal_ignore_and_symlink_warning(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "link.py").symlink_to(tmp_path / "ok.py")
    files = collect_static_files(tmp_path, ())
    assert [f.relative_path for f in files.python_files] == ["ok.py"]
    assert files.ignored_file_count == 2 and files.warnings[0].code == "static_symlinks_skipped"
