"""Regression tests for bounded exception-handler and deferred-body flow."""

from __future__ import annotations

import ast
import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
quality_checker = importlib.import_module("check_no_excuse_rules")
scope_checker = importlib.import_module("check_no_excuse_rules_scope")

HANDLER_ORDER_CASES: Final[tuple[tuple[str, str, frozenset[str]], ...]] = (
    (
        "first_specific_shadows_later_broad",
        "import typing as sp\n"
        "try:\n"
        "    raise RuntimeError\n"
        "except RuntimeError:\n"
        "    pass\n"
        "except Exception:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
        frozenset(),
    ),
    (
        "first_tuple_shadows_later_broad",
        "import typing as sp\n"
        "try:\n"
        "    raise ValueError\n"
        "except (RuntimeError, ValueError):\n"
        "    pass\n"
        "except Exception:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
        frozenset(),
    ),
    (
        "first_exception_shadows_later_specific",
        "import typing as sp\n"
        "try:\n"
        "    raise RuntimeError\n"
        "except Exception:\n"
        "    pass\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
        frozenset(),
    ),
    (
        "later_specific_remains_reachable_after_nonmatching_first",
        "import typing as sp\n"
        "try:\n"
        "    raise RuntimeError\n"
        "except ValueError:\n"
        "    pass\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
        frozenset({"SUBPROCESS_RUN"}),
    ),
)

DEFERRED_BODY_CASES: Final[tuple[tuple[str, str], ...]] = (
    (
        "nested_function",
        "import typing as sp\n"
        "try:\n"
        "    def deferred():\n"
        "        make_value()\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
    ),
    (
        "nested_async_function",
        "import typing as sp\n"
        "try:\n"
        "    async def deferred():\n"
        "        await make_value()\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
    ),
    (
        "nested_lambda",
        "import typing as sp\n"
        "try:\n"
        "    deferred = lambda: make_value()\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
    ),
)

UNKNOWN_HANDLER_CASES: Final[tuple[tuple[str, str, frozenset[str]], ...]] = (
    (
        "unknown_call_keeps_later_broad",
        "import typing as sp\n"
        "try:\n"
        "    make_value()\n"
        "except ValueError:\n"
        "    pass\n"
        "except Exception:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
        frozenset({"SUBPROCESS_RUN"}),
    ),
    (
        "unknown_call_stops_after_exception_catchall",
        "import typing as sp\n"
        "try:\n"
        "    make_value()\n"
        "except Exception:\n"
        "    pass\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
        frozenset(),
    ),
)


def _source_checker() -> Callable[[str, str], tuple[str, ...]]:
    """Load the in-memory checker seam without executing source text."""
    checker: Callable[[str, str], tuple[str, ...]] | None = getattr(
        quality_checker, "violations_from_source", None
    )
    assert checker is not None and callable(checker), "source quality checker is missing"
    return checker


def _has_subprocess_run(tree: ast.AST) -> bool:
    """Query the scope checker for the prohibited call in a constructed tree."""
    checker: Callable[[ast.AST, str, str], bool] | None = getattr(scope_checker, "has_call", None)
    assert checker is not None and callable(checker), "scope quality checker is missing"
    return checker(tree, "subprocess", "run")


def _codes(violations: tuple[str, ...]) -> frozenset[str]:
    """Extract machine issue codes from checker results."""
    return frozenset(item.rsplit(":", maxsplit=1)[-1] for item in violations)


@pytest.mark.parametrize(("case", "source", "expected"), HANDLER_ORDER_CASES)
def test_source_checker_routes_explicit_raise_to_first_compatible_handler(
    case: str,
    source: str,
    expected: frozenset[str],
) -> None:
    # Given: an explicit raise and ordered handlers with distinct binding effects.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, f"handler_order_{case}.py")

    # Then: only the first compatible handler can affect the outgoing scope.
    assert _codes(violations) == expected


def test_source_checker_routes_bare_handler_before_later_synthetic_handler() -> None:
    # Given: valid source with a bare first handler plus a later AST-only handler.
    source = "import typing as sp\ntry:\n    raise RuntimeError\nexcept:\n    pass\nsp.run([])\n"
    tree = ast.parse(source, filename="bare_first.py")
    try_node = tree.body[1]
    assert isinstance(try_node, ast.Try)
    try_node.handlers.append(
        ast.ExceptHandler(
            type=ast.Name(id="RuntimeError", ctx=ast.Load()),
            name=None,
            body=[ast.Import(names=[ast.alias(name="subprocess", asname="sp")])],
        )
    )

    # When: the constructed AST is analyzed without executing source text.
    has_prohibited_call = _has_subprocess_run(tree)

    # Then: the bare first handler shadows the later incompatible route.
    assert has_prohibited_call is False


@pytest.mark.parametrize(("case", "source"), DEFERRED_BODY_CASES)
def test_source_checker_does_not_route_deferred_function_body_risk(
    case: str,
    source: str,
) -> None:
    # Given: a call that exists only in a nested deferred body.
    # When: the enclosing try is analyzed without executing source text.
    violations = _source_checker()(source, f"deferred_body_{case}.py")

    # Then: the enclosing handler is not reachable merely because the body has a call.
    assert violations == ()


@pytest.mark.parametrize(("case", "source", "expected"), UNKNOWN_HANDLER_CASES)
def test_source_checker_preserves_conservative_unknown_exception_paths(
    case: str,
    source: str,
    expected: frozenset[str],
) -> None:
    # Given: an implicit exception risk and ordered handlers with distinct scopes.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, f"unknown_handler_{case}.py")

    # Then: only definitely shadowed unknown paths are removed.
    assert _codes(violations) == expected
