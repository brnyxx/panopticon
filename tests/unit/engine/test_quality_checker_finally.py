"""Behavioral tests for source-quality checker finally composition."""

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

RETURN_THROUGH_FINALLY_SOURCE: Final[str] = (
    "import subprocess as sp\n"
    "def example() -> None:\n"
    "    try:\n"
    "        return\n"
    "    finally:\n"
    "        pass\n"
    "    sp.run([])\n"
)
RAISE_THROUGH_FINALLY_SOURCE: Final[str] = (
    "import subprocess as sp\n"
    "def example() -> None:\n"
    "    try:\n"
    "        raise RuntimeError\n"
    "    finally:\n"
    "        pass\n"
    "    sp.run([])\n"
)
BREAK_THROUGH_FINALLY_SOURCE: Final[str] = (
    "import subprocess as sp\n"
    "import os\n"
    "while True:\n"
    "    try:\n"
    "        break\n"
    "    finally:\n"
    "        pass\n"
    "    sp.run([])\n"
    "else:\n"
    '    os.system("")\n'
)
CONTINUE_THROUGH_FINALLY_SOURCE: Final[str] = (
    "import subprocess as sp\n"
    "import os\n"
    "while ready:\n"
    "    try:\n"
    "        continue\n"
    "    finally:\n"
    "        pass\n"
    "    sp.run([])\n"
    "else:\n"
    '    os.system("")\n'
)
FINALLY_ALIAS_REBIND_SOURCES: Final[tuple[tuple[str, str], ...]] = (
    (
        "normal",
        "import subprocess as sp\ntry:\n    pass\nfinally:\n    import typing as sp\nsp.run([])\n",
    ),
    (
        "break",
        "import subprocess as sp\n"
        "while True:\n"
        "    try:\n"
        "        break\n"
        "    finally:\n"
        "        import typing as sp\n"
        "sp.run([])\n",
    ),
    (
        "continue",
        "import subprocess as sp\n"
        "for _ in [1]:\n"
        "    try:\n"
        "        continue\n"
        "    finally:\n"
        "        import typing as sp\n"
        "sp.run([])\n",
    ),
    (
        "return",
        "def example() -> None:\n"
        "    import subprocess as sp\n"
        "    try:\n"
        "        try:\n"
        "            return\n"
        "        finally:\n"
        "            sp = None\n"
        "    finally:\n"
        "        sp.run([])\n",
    ),
    (
        "raise",
        "def example() -> None:\n"
        "    import subprocess as sp\n"
        "    try:\n"
        "        try:\n"
        "            raise RuntimeError\n"
        "        finally:\n"
        "            sp = None\n"
        "    finally:\n"
        "        sp.run([])\n",
    ),
)
FINALLY_PROHIBITED_CALL_SOURCES: Final[tuple[str, ...]] = (
    "import subprocess as sp\ntry:\n    pass\nfinally:\n    sp.run([])\n",
    "import subprocess as sp\n"
    "def example() -> None:\n"
    "    try:\n"
    "        return\n"
    "    finally:\n"
    "        sp.run([])\n",
    "import subprocess as sp\n"
    "def example() -> None:\n"
    "    try:\n"
    "        raise RuntimeError\n"
    "    finally:\n"
    "        sp.run([])\n",
    "import subprocess as sp\n"
    "while True:\n"
    "    try:\n"
    "        break\n"
    "    finally:\n"
    "        sp.run([])\n",
    "import subprocess as sp\n"
    "while ready:\n"
    "    try:\n"
    "        continue\n"
    "    finally:\n"
    "        sp.run([])\n",
)
FINAL_TERMINATOR_SOURCES: Final[tuple[tuple[str, frozenset[str]], ...]] = (
    (
        "import subprocess as sp\ndef example() -> None:\n"
        "    try:\n"
        "        raise RuntimeError\n"
        "    finally:\n"
        "        return\n"
        "    sp.run([])\n",
        frozenset(),
    ),
    (
        "import subprocess as sp\ndef example() -> None:\n"
        "    try:\n"
        "        return\n"
        "    finally:\n"
        "        raise RuntimeError\n"
        "    sp.run([])\n",
        frozenset(),
    ),
    (
        "import subprocess as sp\nimport os\nimport time\nwhile True:\n"
        "    try:\n"
        "        continue\n"
        "    finally:\n"
        "        break\n"
        "    sp.run([])\n"
        "else:\n"
        '    os.system("")\n'
        "time.sleep(0)\n",
        frozenset({"TIME_SLEEP"}),
    ),
    (
        "import subprocess as sp\nimport os\nwhile ready:\n"
        "    try:\n"
        "        break\n"
        "    finally:\n"
        "        continue\n"
        "    sp.run([])\n"
        "else:\n"
        '    os.system("")\n',
        frozenset({"OS_SYSTEM"}),
    ),
)


def _source_checker() -> Callable[[str, str], tuple[str, ...]]:
    """Load the in-memory checker seam without creating a source file."""
    checker: Callable[[str, str], tuple[str, ...]] | None = getattr(
        quality_checker, "violations_from_source", None
    )
    assert checker is not None and callable(checker), "source quality checker is missing"
    return checker


def _codes(violations: tuple[str, ...]) -> frozenset[str]:
    """Extract machine issue codes from checker results."""
    return frozenset(item.rsplit(":", maxsplit=1)[-1] for item in violations)


def test_source_checker_keeps_following_code_unreachable_after_return_through_finally() -> None:
    # Given: a return followed by a harmless finally block and a prohibited call.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(RETURN_THROUGH_FINALLY_SOURCE, "return_finally.py")

    # Then: the normal finally path cannot fabricate reachability after the return.
    assert violations == ()


def test_source_checker_keeps_following_code_unreachable_after_raise_through_finally() -> None:
    # Given: a raise followed by a harmless finally block and a prohibited call.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(RAISE_THROUGH_FINALLY_SOURCE, "raise_finally.py")

    # Then: the normal finally path cannot fabricate reachability after the raise.
    assert violations == ()


def test_source_checker_keeps_loop_body_and_else_unreachable_after_break_through_finally() -> None:
    # Given: a break through harmless finally with calls after the construct and in loop else.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(BREAK_THROUGH_FINALLY_SOURCE, "break_finally.py")

    # Then: neither the terminated body nor the break-skipped else path is reachable.
    assert violations == ()


def test_source_checker_prunes_body_but_keeps_loop_completion_conservative_after_continue() -> None:
    # Given: a continue through harmless finally and distinct body/else prohibited calls.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(CONTINUE_THROUGH_FINALLY_SOURCE, "continue_finally.py")

    # Then: only conservative loop completion reaches the else call.
    assert _codes(violations) == {"OS_SYSTEM"}


@pytest.mark.parametrize(("path", "source"), FINALLY_ALIAS_REBIND_SOURCES)
def test_source_checker_applies_finally_alias_rebind_to_every_outgoing_path(
    path: str,
    source: str,
) -> None:
    # Given: a harmless finally rebind on a normal, break, continue, return, or raise path.
    # When: the source is analyzed at the first site that can observe that outgoing scope.
    violations = _source_checker()(source, f"finally_alias_{path}.py")

    # Then: no outgoing path retains the prohibited alias after the finally rebind.
    assert violations == ()


@pytest.mark.parametrize("source", FINALLY_PROHIBITED_CALL_SOURCES)
def test_source_checker_always_detects_prohibited_calls_in_finally(source: str) -> None:
    # Given: a prohibited call in finally with each supported incoming outcome shape.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, "prohibited_finally.py")

    # Then: finally itself remains reachable and is always checked.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


@pytest.mark.parametrize(("source", "expected"), FINAL_TERMINATOR_SOURCES)
def test_source_checker_final_terminator_overrides_incoming_outcome(
    source: str,
    expected: frozenset[str],
) -> None:
    # Given: a final return, raise, break, or continue that differs from the incoming outcome.
    # When: the source is analyzed after the finally construct.
    violations = _source_checker()(source, "final_terminator.py")

    # Then: only the final control outcome determines the following reachability.
    assert _codes(violations) == expected


def test_source_checker_preserves_normal_finally_fallthrough() -> None:
    # Given: a normally completing try and normally completing finally before a prohibited call.
    source = "import subprocess as sp\ntry:\n    pass\nfinally:\n    pass\nsp.run([])\n"

    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, "normal_finally.py")

    # Then: normal try/finally still falls through to the following call.
    assert _codes(violations) == {"SUBPROCESS_RUN"}
