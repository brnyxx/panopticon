"""RED contracts for a parsing/rendering-only CLI surface."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from typer.testing import CliRunner

from panopticon.cli.main import NOT_IMPLEMENTED_EXIT, app

ROOT = Path(__file__).resolve().parents[3]
CLI_PATH = ROOT / "src" / "panopticon" / "cli" / "main.py"
runner = CliRunner()
FORBIDDEN_IMPORTS = (
    "panopticon.analyzers",
    "panopticon.discovery",
    "panopticon.findings",
    "panopticon.inventory",
    "panopticon.models",
    "panopticon.probe",
    "panopticon.registry",
    "panopticon.rules",
    "panopticon.sandbox",
    "panopticon.secrets",
    "panopticon.store",
)
STUB_INVOCATIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("watch", ("watch", "target")),
    ("wrap", ("wrap", "--", "echo", "ok")),
    ("install", ("install", "claude")),
    ("uninstall", ("uninstall", "claude")),
    ("fix", ("fix",)),
    ("explain", ("explain", "WATCH-001")),
    ("scan", ("scan", ".")),
    ("ci", ("ci",)),
    ("badge", ("badge",)),
)


def _cli_tree() -> ast.Module:
    """Parse the real CLI module for architectural assertions."""
    source = CLI_PATH.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(CLI_PATH))


def _command(tree: ast.Module, name: str) -> ast.FunctionDef:
    """Return one Typer command function."""
    matches = tuple(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
    )
    assert len(matches) == 1
    return matches[0]


def _call_root(call: ast.Call) -> str | None:
    """Return the left-most name in a call expression."""
    expression: ast.expr = call.func
    while isinstance(expression, ast.Attribute):
        expression = expression.value
    return expression.id if isinstance(expression, ast.Name) else None


def test_cli_imports_only_engine_and_reporter_boundaries() -> None:
    # Given: imports from the real CLI module.
    tree = _cli_tree()
    imported = tuple(
        node.module or alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    ) + tuple(
        alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names
    )

    # Then: CLI owns both boundary seams and no feature implementation import.
    assert any(module.startswith("panopticon.engine") for module in imported)
    assert any(module.startswith("panopticon.reporters") for module in imported)
    assert not any(
        module == forbidden or module.startswith(f"{forbidden}.")
        for module in imported
        for forbidden in FORBIDDEN_IMPORTS
    )


def test_cli_commands_delegate_without_domain_control_flow() -> None:
    # Given: the four foundation pipeline wrappers.
    tree = _cli_tree()
    for name in ("doctor", "watch", "diff", "scan"):
        command = _command(tree, name)
        calls = tuple(node for node in ast.walk(command) if isinstance(node, ast.Call))
        roots = {_call_root(call) for call in calls}

        # When / Then: wrappers call a boundary, not a local feature implementation.
        assert roots & {
            "engine",
            "reporters",
            "run",
            "render",
            "run_diff",
            "render_diff",
        }, name
        assert not any(
            isinstance(node, (ast.For, ast.While, ast.Match, ast.Try)) for node in ast.walk(command)
        )
        assert not any(
            isinstance(node, ast.Call)
            and _call_root(node) in {"persist", "discover", "probe", "sandbox"}
            for node in calls
        )


def test_cli_has_no_print_calls() -> None:
    # Given: the complete CLI AST.
    tree = _cli_tree()

    # Then: user output remains in reporters/typer rendering, never bare print.
    assert not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"
        for node in ast.walk(tree)
    )


def test_non_reporter_source_has_no_bare_print_calls() -> None:
    # Given: product source outside the reporter output package.
    source_root = ROOT / "src" / "panopticon"
    paths = tuple(
        path
        for path in source_root.rglob("*.py")
        if "reporters" not in path.relative_to(source_root).parts
    )

    # Then: the project-wide output boundary is respected.
    assert paths
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
            for node in ast.walk(tree)
        )


def test_version_and_help_are_real_success_surfaces() -> None:
    # Given: the real command entry point.
    version = runner.invoke(app, ["version"])
    help_result = runner.invoke(app, ["--help"])

    # Then: machine-facing surfaces work and enumerate registered commands.
    assert version.exit_code == 0
    assert version.stdout.startswith("pano ")
    assert "schema" in version.stdout
    assert help_result.exit_code == 0
    for command in ("doctor", "watch", "diff", "scan"):
        assert command in help_result.stdout


@pytest.mark.parametrize(("command", "invocation"), STUB_INVOCATIONS, ids=lambda value: value)
def test_unfinished_commands_keep_a_typed_stub_error_surface(
    command: str,
    invocation: tuple[str, ...],
) -> None:
    # Given: a command whose feature epic has not landed yet.
    result = runner.invoke(app, list(invocation))

    # Then: the existing non-feature stub remains deterministic and non-successful.
    assert result.exit_code == NOT_IMPLEMENTED_EXIT, command
