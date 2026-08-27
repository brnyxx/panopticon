"""RED audits for module size, import direction, and test no-excuse rules."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEST_ROOT = ROOT / "tests" / "unit" / "engine"
FORBIDDEN_ENGINE_IMPORTS = (
    "panopticon.cli",
    "panopticon.discovery",
    "panopticon.inventory",
    "panopticon.probe",
    "panopticon.rules",
    "panopticon.sandbox",
    "panopticon.store.gateway",
)


def _pure_loc(path: Path) -> int:
    """Count nonblank, non-line-comment lines using the repository's LOC rule."""
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def _imports(source: str) -> tuple[str, ...]:
    """Collect import module names from Python source."""
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return tuple(names)


def test_engine_and_reporter_modules_stay_under_250_pure_lines() -> None:
    # Given: the foundation package files.
    source_roots = (
        ROOT / "src" / "panopticon" / "engine",
        ROOT / "src" / "panopticon" / "reporters",
    )
    paths = tuple(path for root in source_roots for path in root.rglob("*.py") if path.is_file())

    # Then: a missing foundation package is a contract failure, and no module exceeds the ceiling.
    assert paths
    assert all(_pure_loc(path) <= 250 for path in paths)


def test_engine_import_direction_excludes_feature_execution() -> None:
    # Given: every current engine source file.
    engine_root = ROOT / "src" / "panopticon" / "engine"
    assert engine_root.is_dir()
    paths = tuple(engine_root.rglob("*.py"))
    assert paths

    # Then: engine boundaries do not reach back into CLI or execute feature packages.
    for path in paths:
        imports = _imports(path.read_text(encoding="utf-8"))
        assert not any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for imported in imports
            for forbidden in FORBIDDEN_ENGINE_IMPORTS
        )


def test_new_tests_are_deterministic_and_unsuppressed() -> None:
    # Given: all tests introduced for this checkpoint.
    paths = tuple(TEST_ROOT.glob("test_*.py"))
    assert paths
    sources = tuple(path.read_text(encoding="utf-8") for path in paths)

    # Then: RED tests remain deterministic and local without forbidden runtime calls.
    for source in sources:
        tree = ast.parse(source)
        assert not any(
            isinstance(node, ast.Import) and any(alias.name == "subprocess" for alias in node.names)
            for node in ast.walk(tree)
        )
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
            and node.func.attr == "run"
            for node in ast.walk(tree)
        )
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"sleep", "write_text", "write_bytes"}
            for node in ast.walk(tree)
        )
        assert "# " + "noqa" not in source
        assert "# " + "type: ignore" not in source
        assert "# " + "pyright: ignore" not in source
