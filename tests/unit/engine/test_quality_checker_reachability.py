"""Adversarial reachability tests for the source-quality checker."""

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


LITERAL_UNREACHABLE_SOURCES: tuple[str, ...] = (
    "import subprocess\nif False:\n    subprocess.run([])\n",
    "import subprocess\nif True:\n    pass\nelse:\n    subprocess.run([])\n",
    "import subprocess\nwhile False:\n    subprocess.run([])\n",
)
REACHABLE_LITERAL_SOURCES: tuple[str, ...] = (
    "import subprocess\nif True:\n    subprocess.run([])\n",
    "import subprocess\nif False:\n    pass\nelse:\n    subprocess.run([])\n",
    "import subprocess\nwhile False:\n    pass\nelse:\n    subprocess.run([])\n",
)
EMPTY_LITERAL_ITERABLES: tuple[str, ...] = ("()", "[]", "{}", '""', 'b""')
CONSERVATIVE_ITERABLES: tuple[str, ...] = ("(1,)", "[1]", "{1}", '"x"', 'b"x"', "values")
LOOP_ELSE_TERMINATION_SOURCES: tuple[str, ...] = (
    "import subprocess\nwhile True:\n    break\nelse:\n    subprocess.run([])\n",
    "import subprocess\nfor _ in [1]:\n    break\nelse:\n    subprocess.run([])\n",
)
TERMINATED_FUNCTION_SOURCES: tuple[str, ...] = (
    "import subprocess\ndef example() -> None:\n    return\n    subprocess.run([])\n",
    "import subprocess\ndef example() -> None:\n    raise RuntimeError\n    subprocess.run([])\n",
)
TERMINATED_LOOP_BODY_SOURCES: tuple[str, ...] = (
    "import subprocess\nwhile ready:\n    break\n    subprocess.run([])\n",
    "import subprocess\nfor _ in values:\n    continue\n    subprocess.run([])\n",
)
TERMINATED_BRANCH_SOURCE: Final[str] = (
    "import subprocess\ndef example() -> None:\n"
    "    if ready:\n"
    "        return\n"
    "    else:\n"
    "        raise RuntimeError\n"
    "    subprocess.run([])\n"
)
POST_LOOP_REACHABILITY_SOURCES: tuple[str, ...] = (
    "import subprocess\nfor _ in []:\n    pass\nsubprocess.run([])\n",
    "import subprocess\nwhile False:\n    pass\nsubprocess.run([])\n",
    "import subprocess as sp\nwhile ready:\n    import typing as sp\nsp.run([])\n",
)
REACHABLE_TERMINATION_SOURCES: tuple[str, ...] = (
    "import subprocess\nfor _ in []:\n    pass\nelse:\n    subprocess.run([])\n",
    "import subprocess\nfor _ in values:\n    pass\nelse:\n    subprocess.run([])\n",
    "import subprocess\nwhile ready:\n    pass\nelse:\n    subprocess.run([])\n",
    (
        "import subprocess\nfor _ in [1]:\n"
        "    if ready:\n        break\n"
        "else:\n    subprocess.run([])\n"
    ),
    (
        "import subprocess\ndef example() -> None:\n"
        "    if ready:\n        return\n"
        "    subprocess.run([])\n"
    ),
    "import subprocess\ndef example() -> None:\n    subprocess.run([])\n    return\n",
    "import subprocess\nwhile ready:\n    subprocess.run([])\n    break\n",
    "import subprocess\nwhile ready:\n    subprocess.run([])\n    continue\n",
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


@pytest.mark.parametrize("source", LITERAL_UNREACHABLE_SOURCES)
def test_source_checker_skips_calls_in_unreachable_literal_paths(source: str) -> None:
    # Given: a prohibited call exclusively in a statically unreachable path.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, "unreachable_literal.py")

    # Then: dead code cannot create a finding.
    assert violations == ()


@pytest.mark.parametrize("source", REACHABLE_LITERAL_SOURCES)
def test_source_checker_detects_calls_in_reachable_literal_paths(source: str) -> None:
    # Given: a prohibited call in the selected branch or reachable loop else.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, "reachable_literal.py")

    # Then: selected literal paths remain checked.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


@pytest.mark.parametrize("iterable", EMPTY_LITERAL_ITERABLES)
def test_source_checker_skips_empty_literal_for_body(iterable: str) -> None:
    # Given: a prohibited call only in an empty literal for body.
    source = f"import subprocess\nfor _ in {iterable}:\n    subprocess.run([])\n"

    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, "empty_literal_body.py")

    # Then: the statically empty body is not visited.
    assert violations == ()


@pytest.mark.parametrize("iterable", EMPTY_LITERAL_ITERABLES)
def test_source_checker_analyzes_empty_literal_for_else(iterable: str) -> None:
    # Given: an empty literal for whose else contains a prohibited call.
    source = f"import subprocess\nfor _ in {iterable}:\n    pass\nelse:\n    subprocess.run([])\n"

    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, "empty_literal_else.py")

    # Then: the else path is checked because it executes for an empty iterable.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


@pytest.mark.parametrize("iterable", CONSERVATIVE_ITERABLES)
def test_source_checker_remains_conservative_for_nonempty_or_dynamic_for(
    iterable: str,
) -> None:
    # Given: a nonempty or dynamic iterable with a prohibited loop-body call.
    source = f"import subprocess\nfor _ in {iterable}:\n    subprocess.run([])\n"

    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, "conservative_for.py")

    # Then: the potentially reachable body remains checked.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


@pytest.mark.parametrize("source", LOOP_ELSE_TERMINATION_SOURCES)
def test_source_checker_skips_unreachable_loop_else_after_unconditional_break(
    source: str,
) -> None:
    # Given: an unconditional break before a prohibited loop-else call.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, "terminated_loop_else.py")

    # Then: the loop else is unreachable and cannot create a finding.
    assert violations == ()


@pytest.mark.parametrize("source", TERMINATED_FUNCTION_SOURCES)
def test_source_checker_skips_calls_after_unconditional_function_terminators(
    source: str,
) -> None:
    # Given: a prohibited call after an unconditional return or raise.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, "terminated_function.py")

    # Then: the terminated function path does not reach the call.
    assert violations == ()


@pytest.mark.parametrize("source", TERMINATED_LOOP_BODY_SOURCES)
def test_source_checker_skips_calls_after_unconditional_loop_terminators(
    source: str,
) -> None:
    # Given: a prohibited call after an unconditional break or continue in a loop body.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, "terminated_loop_body.py")

    # Then: the loop body path stops at its terminator.
    assert violations == ()


def test_source_checker_skips_call_after_terminating_if_branches() -> None:
    # Given: both reachable branches terminate before a prohibited call.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(TERMINATED_BRANCH_SOURCE, "terminated_branches.py")

    # Then: no path reaches the following call.
    assert violations == ()


@pytest.mark.parametrize("source", REACHABLE_TERMINATION_SOURCES)
def test_source_checker_detects_reachable_calls_around_terminators(source: str) -> None:
    # Given: a reachable prohibited call in an empty/dynamic loop, branch, or prefix.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, "reachable_termination.py")

    # Then: conservative paths and calls before terminators remain checked.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


@pytest.mark.parametrize("source", POST_LOOP_REACHABILITY_SOURCES)
def test_source_checker_keeps_zero_iteration_paths_after_loops(source: str) -> None:
    # Given: a prohibited call after an empty, literal-false, or dynamic loop.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, "post_loop_reachability.py")

    # Then: a path that skips the loop still reaches the following call.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


def test_source_checker_rebinds_capture_before_match_guard_and_body() -> None:
    # Given: a capture named like a prohibited module alias, used in guard and body.
    source = (
        "import subprocess as sp\nmatch value:\n    case sp if sp.run([]):\n        sp.run([])\n"
    )

    # When: the source is analyzed across the capture binding.
    violations = _source_checker()(source, "match_capture_guard_body.py")

    # Then: calls use the captured subject, not the earlier imported module.
    assert violations == ()


def test_source_checker_rebinds_capture_after_irrefutable_match_case() -> None:
    # Given: an irrefutable capture that shadows a prohibited module alias.
    source = "import subprocess as sp\nmatch value:\n    case sp:\n        sp.run([])\nsp.run([])\n"

    # When: the source is analyzed after the reachable match case.
    violations = _source_checker()(source, "match_capture_after.py")

    # Then: both the case body and post-match call use the capture binding.
    assert violations == ()


def test_source_checker_treats_literal_true_wildcard_guard_as_irrefutable() -> None:
    # Given: a wildcard case with a literal-True guard and harmless rebinding.
    source = (
        "import subprocess as sp\n"
        "match value:\n"
        "    case _ if True:\n"
        "        import typing as sp\n"
        "sp.run([])\n"
    )

    # When: the source is analyzed after the reachable case.
    violations = _source_checker()(source, "match_true_guard.py")

    # Then: no impossible no-match provenance survives the irrefutable case.
    assert violations == ()


def test_source_checker_skips_literal_false_match_guard_and_continues() -> None:
    # Given: a prohibited call only in a literal-False case followed by a harmless wildcard.
    source = (
        "import subprocess as sp\n"
        "match value:\n"
        "    case _ if False:\n"
        "        sp.run([])\n"
        "    case _:\n"
        "        import typing as sp\n"
        "sp.run([])\n"
    )

    # When: the source is analyzed through the match cases.
    violations = _source_checker()(source, "match_false_guard.py")

    # Then: the false-guard body is skipped and the next case controls the join.
    assert violations == ()


def test_source_checker_allows_harmless_reachable_match_paths() -> None:
    # Given: all reachable paths harmlessly rebind the prohibited alias.
    source = (
        "import subprocess as sp\n"
        "match value:\n"
        "    case 0 if False:\n"
        "        sp.run([])\n"
        "    case captured if True:\n"
        "        import typing as sp\n"
        "sp.run([])\n"
    )

    # When: the source is analyzed with literal guard reachability.
    violations = _source_checker()(source, "match_all_harmless.py")

    # Then: dead and impossible alternatives do not create a finding.
    assert violations == ()


def test_source_checker_flags_one_reachable_prohibited_match_path() -> None:
    # Given: an unreachable harmless-looking case and a reachable prohibited wildcard path.
    source = (
        "import subprocess as sp\n"
        "match value:\n"
        "    case 0 if False:\n"
        "        pass\n"
        "    case _:\n"
        "        sp.run([])\n"
    )

    # When: the source is analyzed through the match cases.
    violations = _source_checker()(source, "match_one_prohibited.py")

    # Then: the reachable prohibited path is still reported.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


def test_source_checker_joins_match_capture_with_possible_fallthrough() -> None:
    # Given: a guarded capture may be harmless, but fallthrough preserves the old alias.
    source = (
        "import subprocess as sp\n"
        "match value:\n"
        "    case captured if ready:\n"
        "        import typing as sp\n"
        "    case _:\n"
        "        pass\n"
        "sp.run([])\n"
    )

    # When: the source is analyzed after the conservative match join.
    violations = _source_checker()(source, "match_capture_join.py")

    # Then: the possible prohibited provenance is retained.
    assert _codes(violations) == {"SUBPROCESS_RUN"}
