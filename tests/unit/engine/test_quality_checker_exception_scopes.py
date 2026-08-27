"""Behavioral tests for bounded exception-flow scope handling."""

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

EXCEPTION_SCOPE_CASES: Final[tuple[tuple[str, str, frozenset[str]], ...]] = (
    (
        "explicit_raise_after_harmless_rebind",
        "import subprocess as sp\n"
        "try:\n"
        "    sp = None\n"
        "    raise RuntimeError\n"
        "except RuntimeError:\n"
        "    pass\n"
        "sp.run([])\n",
        frozenset(),
    ),
    (
        "explicit_raise_with_prohibited_binding",
        "import subprocess as sp\n"
        "try:\n"
        "    raise RuntimeError\n"
        "except RuntimeError:\n"
        "    pass\n"
        "sp.run([])\n",
        frozenset({"SUBPROCESS_RUN"}),
    ),
    (
        "raise_paths_join_conservatively",
        "import subprocess as sp\n"
        "try:\n"
        "    if ready:\n"
        "        sp = None\n"
        "        raise RuntimeError\n"
        "    else:\n"
        "        raise RuntimeError\n"
        "except RuntimeError:\n"
        "    pass\n"
        "sp.run([])\n",
        frozenset({"SUBPROCESS_RUN"}),
    ),
    (
        "handler_rebind_survives_handler_exit",
        "import subprocess as sp\n"
        "try:\n"
        "    raise RuntimeError\n"
        "except RuntimeError:\n"
        "    import typing as sp\n"
        "sp.run([])\n",
        frozenset(),
    ),
    (
        "matching_raise_tuple_handler",
        "import subprocess as sp\n"
        "try:\n"
        "    sp = None\n"
        "    raise RuntimeError\n"
        "except (ValueError, RuntimeError):\n"
        "    pass\n"
        "sp.run([])\n",
        frozenset(),
    ),
    (
        "unmatched_raise_tuple_keeps_following_code_unreachable",
        "import subprocess as sp\n"
        "try:\n"
        "    raise RuntimeError\n"
        "except (ValueError, KeyError):\n"
        "    pass\n"
        "sp.run([])\n",
        frozenset(),
    ),
    (
        "implicit_raise_keeps_pre_try_handler_alternative",
        "import subprocess as sp\n"
        "try:\n"
        "    make_value()\n"
        "except RuntimeError:\n"
        "    pass\n"
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


@pytest.mark.parametrize(("case", "source", "expected"), EXCEPTION_SCOPE_CASES)
def test_source_checker_preserves_bounded_exception_scope_semantics(
    case: str,
    source: str,
    expected: frozenset[str],
) -> None:
    # Given: one explicit/implicit exception-flow scope case and its expected findings.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, f"exception_scope_{case}.py")

    # Then: only the machine findings reachable under that bounded flow are reported.
    assert _codes(violations) == expected
