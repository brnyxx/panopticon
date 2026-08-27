"""Regression tests for handler and else exceptions crossing their own finally."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from textwrap import dedent
from typing import Final

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
quality_checker = importlib.import_module("check_no_excuse_rules")

HANDLER_FINALLY_CASES: Final[tuple[tuple[str, str, frozenset[str]], ...]] = (
    (
        "handler_raise_scope_is_rebound_by_own_finally",
        dedent(
            """\
            import typing as sp
            try:
                try:
                    raise ValueError
                except ValueError:
                    import subprocess as sp
                    raise RuntimeError
                finally:
                    sp = None
            except RuntimeError:
                pass
            sp.run([])
            """
        ),
        frozenset(),
    ),
    (
        "handler_raise_observes_own_finally_scope",
        dedent(
            """\
            import typing as sp
            try:
                try:
                    raise ValueError
                except ValueError:
                    import typing as sp
                    raise RuntimeError
                finally:
                    import subprocess as sp
            except RuntimeError:
                pass
            sp.run([])
            """
        ),
        frozenset({"SUBPROCESS_RUN"}),
    ),
    (
        "terminating_finally_replaces_stale_handler_exception",
        dedent(
            """\
            import typing as sp
            try:
                try:
                    raise ValueError
                except ValueError:
                    raise RuntimeError
                finally:
                    raise KeyError
            except RuntimeError:
                import subprocess as sp
            except KeyError:
                pass
            sp.run([])
            """
        ),
        frozenset(),
    ),
    (
        "nested_handler_try_finally_reaches_enclosing_finally",
        dedent(
            """\
            import typing as sp
            try:
                try:
                    raise ValueError
                except ValueError:
                    try:
                        import subprocess as sp
                        raise RuntimeError
                    finally:
                        sp = None
                finally:
                    pass
            except RuntimeError:
                pass
            sp.run([])
            """
        ),
        frozenset(),
    ),
    (
        "handler_unknown_exception_scope_is_rebound_by_own_finally",
        dedent(
            """\
            import typing as sp
            try:
                try:
                    raise ValueError
                except ValueError:
                    import subprocess as sp
                    unknown()
                finally:
                    sp = None
            except RuntimeError:
                pass
            sp.run([])
            """
        ),
        frozenset(),
    ),
    (
        "else_raise_scope_is_rebound_by_own_finally",
        dedent(
            """\
            import typing as sp
            try:
                try:
                    pass
                except ValueError:
                    pass
                else:
                    import subprocess as sp
                    raise RuntimeError
                finally:
                    sp = None
            except RuntimeError:
                pass
            sp.run([])
            """
        ),
        frozenset(),
    ),
    (
        "else_raise_observes_own_finally_scope",
        dedent(
            """\
            import typing as sp
            try:
                try:
                    pass
                except ValueError:
                    pass
                else:
                    import typing as sp
                    raise RuntimeError
                finally:
                    import subprocess as sp
            except RuntimeError:
                pass
            sp.run([])
            """
        ),
        frozenset({"SUBPROCESS_RUN"}),
    ),
)

CONTROL_CASES: Final[tuple[tuple[str, str, frozenset[str]], ...]] = (
    (
        "body_exception_uses_current_handlers",
        dedent(
            """\
            import typing as sp
            try:
                import subprocess as sp
                raise RuntimeError
            except RuntimeError:
                pass
            sp.run([])
            """
        ),
        frozenset({"SUBPROCESS_RUN"}),
    ),
    (
        "finally_exception_bypasses_current_handlers",
        dedent(
            """\
            import typing as sp
            try:
                try:
                    pass
                except RuntimeError:
                    import subprocess as sp
                finally:
                    raise RuntimeError
            except RuntimeError:
                pass
            sp.run([])
            """
        ),
        frozenset(),
    ),
    (
        "matched_inner_handler_consumes_exception",
        dedent(
            """\
            import typing as sp
            try:
                try:
                    raise RuntimeError
                except RuntimeError:
                    pass
            except RuntimeError:
                import subprocess as sp
            sp.run([])
            """
        ),
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


def _codes(violations: tuple[str, ...]) -> frozenset[str]:
    """Extract machine issue codes from checker results."""
    return frozenset(item.rsplit(":", maxsplit=1)[-1] for item in violations)


@pytest.mark.parametrize("case, source, expected", HANDLER_FINALLY_CASES)
def test_source_checker_composes_handler_and_else_exceptions_through_finally(
    case: str,
    source: str,
    expected: frozenset[str],
) -> None:
    # Given: an exception originating in a handler or else block and a sibling outer handler.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, f"handler_finally_{case}.py")

    # Then: the outgoing exception reaches the outer handler only with its own-finally scope.
    assert _codes(violations) == expected


@pytest.mark.parametrize("case, source, expected", CONTROL_CASES)
def test_source_checker_preserves_existing_exception_stage_controls(
    case: str,
    source: str,
    expected: frozenset[str],
) -> None:
    # Given: a body exception, a finally exception, or a matched inner handler.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, f"handler_finally_control_{case}.py")

    # Then: existing handler ownership and final-exception override semantics remain intact.
    assert _codes(violations) == expected
