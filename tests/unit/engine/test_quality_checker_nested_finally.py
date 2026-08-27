"""Regression tests for nested-finally exception propagation and pairing."""

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

NESTED_FINALLY_PROPAGATION_CASES: Final[tuple[tuple[str, str, frozenset[str]], ...]] = (
    (
        "unknown_call_reaches_outer_handler",
        "import typing as sp\n"
        "try:\n"
        "    try:\n"
        "        pass\n"
        "    finally:\n"
        "        unknown()\n"
        "        sp = None\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
        frozenset({"SUBPROCESS_RUN"}),
    ),
    (
        "explicit_raise_reaches_outer_handler",
        "import typing as sp\n"
        "try:\n"
        "    try:\n"
        "        pass\n"
        "    finally:\n"
        "        raise RuntimeError\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
        frozenset({"SUBPROCESS_RUN"}),
    ),
)

NEAREST_HANDLER_CASES: Final[tuple[tuple[str, str, frozenset[str]], ...]] = (
    (
        "handled_unknown_call_stays_inner",
        "import typing as sp\n"
        "try:\n"
        "    try:\n"
        "        unknown()\n"
        "    except Exception:\n"
        "        pass\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
        frozenset(),
    ),
    (
        "handled_raise_stays_inner",
        "import typing as sp\n"
        "try:\n"
        "    try:\n"
        "        raise RuntimeError\n"
        "    except RuntimeError:\n"
        "        pass\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
        frozenset(),
    ),
    (
        "unmatched_unknown_call_reaches_outer_handler",
        "import typing as sp\n"
        "try:\n"
        "    try:\n"
        "        unknown()\n"
        "    except ValueError:\n"
        "        pass\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
        frozenset({"SUBPROCESS_RUN"}),
    ),
    (
        "unmatched_raise_reaches_outer_handler",
        "import typing as sp\n"
        "try:\n"
        "    try:\n"
        "        raise ValueError\n"
        "    except RuntimeError:\n"
        "        pass\n"
        "except ValueError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
        frozenset({"SUBPROCESS_RUN"}),
    ),
)

ALL_HARMLESS_OUTGOING_SOURCE: Final[str] = (
    "import subprocess as sp\n"
    "try:\n"
    "    try:\n"
    "        if ready:\n"
    "            sp = None\n"
    "            raise ValueError\n"
    "        else:\n"
    "            raise RuntimeError\n"
    "    finally:\n"
    "        pass\n"
    "except ValueError:\n"
    "    pass\n"
    "except RuntimeError:\n"
    "    import typing as sp\n"
    "sp.run([])\n"
)
INVERSE_ONE_PROHIBITED_SOURCE: Final[str] = (
    "import subprocess as sp\n"
    "try:\n"
    "    try:\n"
    "        if ready:\n"
    "            raise ValueError\n"
    "        else:\n"
    "            sp = None\n"
    "            raise RuntimeError\n"
    "    finally:\n"
    "        pass\n"
    "except ValueError:\n"
    "    pass\n"
    "except RuntimeError:\n"
    "    import typing as sp\n"
    "sp.run([])\n"
)
NORMAL_FINALLY_REBIND_SOURCE: Final[str] = (
    "import subprocess as sp\n"
    "try:\n"
    "    try:\n"
    "        if ready:\n"
    "            sp = None\n"
    "            raise ValueError\n"
    "        else:\n"
    "            raise RuntimeError\n"
    "    finally:\n"
    "        if cleanup:\n"
    "            sp = None\n"
    "except ValueError:\n"
    "    pass\n"
    "except RuntimeError:\n"
    "    import typing as sp\n"
    "sp.run([])\n"
)
TERMINATING_FINALLY_SOURCE: Final[str] = (
    "import typing as sp\n"
    "try:\n"
    "    try:\n"
    "        if ready:\n"
    "            raise ValueError\n"
    "        else:\n"
    "            raise RuntimeError\n"
    "    finally:\n"
    "        import subprocess as sp\n"
    "        raise KeyError\n"
    "except ValueError:\n"
    "    pass\n"
    "except RuntimeError:\n"
    "    import typing as sp\n"
    "except KeyError:\n"
    "    pass\n"
    "sp.run([])\n"
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


@pytest.mark.parametrize(("case", "source", "expected"), NESTED_FINALLY_PROPAGATION_CASES)
def test_source_checker_propagates_nested_finally_exception_paths(
    case: str,
    source: str,
    expected: frozenset[str],
) -> None:
    # Given: an unknown call or explicit raise in an inner finally.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, f"nested_finally_{case}.py")

    # Then: the enclosing handler remains reachable through that exception path.
    assert _codes(violations) == expected


@pytest.mark.parametrize(("case", "source", "expected"), NEAREST_HANDLER_CASES)
def test_source_checker_routes_nested_exception_to_nearest_matching_handler(
    case: str,
    source: str,
    expected: frozenset[str],
) -> None:
    # Given: a call or raise with either a matching or nonmatching inner handler.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, f"nearest_handler_{case}.py")

    # Then: matched paths stop at the inner handler and unmatched paths propagate.
    assert _codes(violations) == expected


def test_source_checker_preserves_each_exception_scope_through_harmless_finally() -> None:
    # Given: the verifier's exact branch-paired all-harmless outgoing example.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(ALL_HARMLESS_OUTGOING_SOURCE, "all_harmless_outgoing.py")

    # Then: each exception retains the scope from its own branch.
    assert violations == ()


def test_source_checker_detects_one_prohibited_branch_after_harmless_finally() -> None:
    # Given: the inverse branch pair with one prohibited outgoing scope.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(INVERSE_ONE_PROHIBITED_SOURCE, "one_prohibited_outgoing.py")

    # Then: the remaining prohibited path is reported.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


def test_source_checker_rebinds_finally_independently_for_each_exception_path() -> None:
    # Given: a conditional normal finally rebind and distinct incoming scopes.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(NORMAL_FINALLY_REBIND_SOURCE, "finally_rebind_paths.py")

    # Then: the rebind is paired with each incoming exception rather than cross-produced.
    assert violations == ()


def test_source_checker_overrides_each_incoming_path_with_terminating_finally_raise() -> None:
    # Given: two incoming exception types and a typed finally exception with its own scope.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(TERMINATING_FINALLY_SOURCE, "terminating_finally_paths.py")

    # Then: the final KeyError path reaches its handler with the final scope.
    assert _codes(violations) == {"SUBPROCESS_RUN"}
