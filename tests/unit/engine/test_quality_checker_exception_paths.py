"""Regression tests for reachable exception-path provenance."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
quality_checker = importlib.import_module("check_no_excuse_rules")

IMPLICIT_SCOPE_CASES: Final[tuple[tuple[str, str, frozenset[str]], ...]] = (
    (
        "risk_scope_at_call_point",
        "import typing as sp\n"
        "try:\n"
        "    import subprocess as sp\n"
        "    unknown()\n"
        "    sp = object()\n"
        "except ValueError:\n"
        "    pass\n"
        "sp.run([])\n",
        frozenset({"SUBPROCESS_RUN"}),
    ),
    (
        "harmless_rebind_before_call_point",
        "import typing as sp\n"
        "try:\n"
        "    sp = None\n"
        "    unknown()\n"
        "except ValueError:\n"
        "    pass\n"
        "sp.run([])\n",
        frozenset(),
    ),
    (
        "nested_handler_risk_reaches_outer_handler",
        "import typing as sp\n"
        "try:\n"
        "    try:\n"
        "        raise ValueError\n"
        "    except ValueError:\n"
        "        unknown()\n"
        "        sp = None\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
        frozenset({"SUBPROCESS_RUN"}),
    ),
    (
        "orelse_risk_skips_current_handlers",
        "import typing as sp\n"
        "try:\n"
        "    try:\n"
        "        pass\n"
        "    except ValueError:\n"
        "        import subprocess as sp\n"
        "    else:\n"
        "        unknown()\n"
        "except RuntimeError:\n"
        "    pass\n"
        "sp.run([])\n",
        frozenset(),
    ),
)

UNREACHABLE_EXCEPTION_RISK_CASES: Final[tuple[tuple[str, str], ...]] = (
    (
        "raise_expression",
        "import typing as sp\n"
        "def example() -> None:\n"
        "    try:\n"
        "        raise RuntimeError\n"
        "        unknown()\n"
        "    except ValueError:\n"
        "        import subprocess as sp\n"
        "    sp.run([])\n",
    ),
    (
        "raise_import",
        "import typing as sp\n"
        "def example() -> None:\n"
        "    try:\n"
        "        raise RuntimeError\n"
        "        import module_name\n"
        "    except ValueError:\n"
        "        import subprocess as sp\n"
        "    sp.run([])\n",
    ),
    (
        "raise_definition_time",
        "import typing as sp\n"
        "def example() -> None:\n"
        "    try:\n"
        "        raise RuntimeError\n"
        "        @make_decorator()\n"
        "        def deferred():\n"
        "            pass\n"
        "    except ValueError:\n"
        "        import subprocess as sp\n"
        "    sp.run([])\n",
    ),
    (
        "return_expression",
        "import typing as sp\n"
        "def example() -> None:\n"
        "    try:\n"
        "        return\n"
        "        unknown()\n"
        "    except ValueError:\n"
        "        import subprocess as sp\n"
        "    sp.run([])\n",
    ),
    (
        "return_import",
        "import typing as sp\n"
        "def example() -> None:\n"
        "    try:\n"
        "        return\n"
        "        import module_name\n"
        "    except ValueError:\n"
        "        import subprocess as sp\n"
        "    sp.run([])\n",
    ),
    (
        "return_definition_time",
        "import typing as sp\n"
        "def example() -> None:\n"
        "    try:\n"
        "        return\n"
        "        @make_decorator()\n"
        "        def deferred():\n"
        "            pass\n"
        "    except ValueError:\n"
        "        import subprocess as sp\n"
        "    sp.run([])\n",
    ),
)

PATH_PAIR_CASES: Final[tuple[tuple[str, str, frozenset[str]], ...]] = (
    (
        "matching_exception_scopes_are_harmless",
        "import subprocess as sp\n"
        "try:\n"
        "    if ready:\n"
        "        sp = None\n"
        "        raise ValueError\n"
        "    else:\n"
        "        raise RuntimeError\n"
        "except ValueError:\n"
        "    pass\n"
        "except RuntimeError:\n"
        "    import typing as sp\n"
        "sp.run([])\n",
        frozenset(),
    ),
    (
        "one_matching_exception_scope_is_prohibited",
        "import subprocess as sp\n"
        "try:\n"
        "    if ready:\n"
        "        raise ValueError\n"
        "    else:\n"
        "        sp = None\n"
        "        raise RuntimeError\n"
        "except ValueError:\n"
        "    pass\n"
        "except RuntimeError:\n"
        "    import typing as sp\n"
        "sp.run([])\n",
        frozenset({"SUBPROCESS_RUN"}),
    ),
)


def _source_checker() -> Callable[[str, str], tuple[str, ...]]:
    """Load the in-memory checker seam without executing source text."""
    checker: Callable[[str, str], tuple[str, ...]] | None = getattr(
        quality_checker, "violations_from_source", None
    )
    assert checker is not None and callable(checker), "source quality checker is missing"
    return checker


def _codes(violations: tuple[str, ...]) -> frozenset[str]:
    """Extract machine issue codes from checker results."""
    return frozenset(item.rsplit(":", maxsplit=1)[-1] for item in violations)


@pytest.mark.parametrize("case, source, expected", IMPLICIT_SCOPE_CASES)
def test_source_checker_captures_implicit_risk_scope_at_risk_point(
    case: str,
    source: str,
    expected: frozenset[str],
) -> None:
    # Given: an implicit exception risk whose binding differs from the enclosing scope.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, f"implicit_scope_{case}.py")

    # Then: handler routing uses the binding at the risk point.
    assert _codes(violations) == expected


@pytest.mark.parametrize("case, source", UNREACHABLE_EXCEPTION_RISK_CASES)
def test_source_checker_ignores_unreachable_exception_risks(
    case: str,
    source: str,
) -> None:
    # Given: an exception risk after a terminating statement in a try body.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, f"unreachable_{case}.py")

    # Then: syntax after the terminator cannot fabricate a handler path.
    assert violations == ()


@pytest.mark.parametrize("case, source, expected", PATH_PAIR_CASES)
def test_source_checker_keeps_exception_type_and_scope_paired(
    case: str,
    source: str,
    expected: frozenset[str],
) -> None:
    # Given: distinct explicit exception branches with distinct binding scopes.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, f"path_pair_{case}.py")

    # Then: each scope reaches only handlers compatible with its own exception type.
    assert _codes(violations) == expected
