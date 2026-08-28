"""RED contracts for engine and reporter Protocol-only seams."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _module_source(module_name: str) -> tuple[Path, ast.Module]:
    """Read one expected seam module without making collection depend on it."""
    try:
        spec = importlib.util.find_spec(module_name)
    except ModuleNotFoundError:
        spec = None
    assert spec is not None and spec.origin is not None, f"missing protocol module: {module_name}"
    path = Path(spec.origin)
    return path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    """Find one class definition by its public name."""
    matches = tuple(
        node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == name
    )
    assert len(matches) == 1, f"missing unique protocol {name}"
    return matches[0]


def test_reporter_is_a_sanitized_render_protocol() -> None:
    # Given: the reporter boundary module.
    path, tree = _module_source("panopticon.reporters.base")
    reporter = _class(tree, "Reporter")
    bases = {ast.unparse(base) for base in reporter.bases}
    methods = tuple(
        node for node in reporter.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    source = path.read_text(encoding="utf-8")

    # Then: reporters expose only a typed render seam and cannot bypass persistence/leak policy.
    assert "Protocol" in bases
    render = tuple(method for method in methods if method.name == "render")
    assert len(render) == 1
    assert render[0].returns is not None
    assert "Render" in ast.unparse(render[0].returns)
    assert "panopticon.store.gateway" not in source
    assert "panopticon.util.leak_check" not in source


def test_engine_and_reporter_orchestration_avoids_unsafe_side_effects() -> None:
    # Given: each engine and reporter orchestration module.
    module_names = (
        "panopticon.engine.contracts",
        "panopticon.engine.doctor",
        "panopticon.engine.watch",
        "panopticon.engine.diff",
        "panopticon.engine.scan",
        "panopticon.reporters.base",
    )
    trees = tuple(_module_source(name)[1] for name in module_names)

    # Then: orchestration may compose features but never shells, prints, or writes directly.
    for tree in trees:
        assert not any(
            isinstance(node, ast.Import) and any(alias.name == "subprocess" for alias in node.names)
            for node in ast.walk(tree)
        )
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"print", "eval", "exec", "open"}
            for node in ast.walk(tree)
        )


def test_engine_package_is_not_allowed_to_import_the_cli() -> None:
    # Given: all available source modules below engine/.
    engine_path = ROOT / "src" / "panopticon" / "engine"
    assert engine_path.is_dir(), "engine package is missing"
    sources = tuple(path.read_text(encoding="utf-8") for path in engine_path.rglob("*.py"))

    # Then: dependency direction is one-way from CLI into engine.
    assert sources
    assert not any("panopticon.cli" in source for source in sources)
