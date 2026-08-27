"""Behavioral tests for source-quality checker scope joins and barriers."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
quality_checker = importlib.import_module("check_no_excuse_rules")


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


def test_source_checker_retains_binding_through_false_branch() -> None:
    # Given: a prohibited alias followed by an unreachable harmless rebind.
    source = "import subprocess as sp\nif False:\n    import typing as sp\nsp.run([])\n"

    # When: the source is analyzed in source order.
    violations = _source_checker()(source, "false_branch.py")

    # Then: the possible pre-branch prohibited binding remains observable.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


def test_source_checker_retains_binding_after_empty_for_loop() -> None:
    # Given: a prohibited alias followed by a loop that may not execute.
    source = "import subprocess as sp\nfor sp in ():\n    pass\nsp.run([])\n"

    # When: the source is analyzed across the loop boundary.
    violations = _source_checker()(source, "empty_loop.py")

    # Then: the possible pre-loop prohibited binding remains observable.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


@pytest.mark.parametrize(
    "source",
    (
        "import subprocess as sp\n"
        "if ready:\n"
        "    import typing as sp\n"
        "else:\n"
        "    pass\n"
        "sp.run([])\n",
        "import subprocess as sp\nif ready:\n    import typing as sp\nsp.run([])\n",
    ),
)
def test_source_checker_merges_possible_bindings_across_if_paths(source: str) -> None:
    # Given: a dynamic branch that rebinds a prohibited alias on only some paths.
    # When: the source is analyzed after both paths join.
    violations = _source_checker()(source, "dynamic_if.py")

    # Then: possible prohibited provenance is retained conservatively.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


def test_source_checker_merges_possible_bindings_after_dynamic_while() -> None:
    # Given: a prohibited alias and a loop that may execute zero times.
    source = "import subprocess as sp\nwhile ready:\n    import typing as sp\nsp.run([])\n"

    # When: the source is analyzed after the loop.
    violations = _source_checker()(source, "dynamic_while.py")

    # Then: the pre-loop prohibited provenance remains possible.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


def test_source_checker_merges_possible_bindings_across_try_handler() -> None:
    # Given: a try branch that rebinds and an exception path that leaves the alias intact.
    source = (
        "import subprocess as sp\n"
        "try:\n"
        "    import typing as sp\n"
        "except ImportError:\n"
        "    pass\n"
        "sp.run([])\n"
    )

    # When: the source is analyzed after the handler join.
    violations = _source_checker()(source, "try_handler.py")

    # Then: the possible prohibited handler provenance is retained.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


def test_source_checker_merges_possible_bindings_across_match_cases() -> None:
    # Given: a match case that rebinds and a wildcard case that leaves the alias intact.
    source = (
        "import subprocess as sp\n"
        "match value:\n"
        "    case 0:\n"
        "        import typing as sp\n"
        "    case _:\n"
        "        pass\n"
        "sp.run([])\n"
    )

    # When: the source is analyzed after the cases join.
    violations = _source_checker()(source, "match_cases.py")

    # Then: the possible prohibited case provenance is retained.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


def test_source_checker_allows_rebinding_on_every_if_path() -> None:
    # Given: every branch rebinds a prohibited alias to a harmless module.
    source = (
        "import subprocess as sp\n"
        "if ready:\n"
        "    import typing as sp\n"
        "else:\n"
        "    import typing as sp\n"
        "sp.run([])\n"
    )

    # When: the source is analyzed after the complete branch join.
    violations = _source_checker()(source, "all_if_paths.py")

    # Then: no prohibited provenance remains possible.
    assert violations == ()


def test_source_checker_ignores_unreachable_true_false_alternative() -> None:
    # Given: a reachable harmless binding and a prohibited binding in an unreachable branch.
    source = (
        "import typing as sp\nif True:\n    pass\nelse:\n    import subprocess as sp\nsp.run([])\n"
    )

    # When: the source is analyzed with literal branch conditions.
    violations = _source_checker()(source, "literal_branch.py")

    # Then: unreachable prohibited provenance does not create a finding.
    assert violations == ()


def test_source_checker_allows_rebinding_on_try_and_handler_paths() -> None:
    # Given: both normal and exception paths rebind the alias harmlessly.
    source = (
        "import subprocess as sp\n"
        "try:\n"
        "    import typing as sp\n"
        "except ImportError:\n"
        "    import typing as sp\n"
        "sp.run([])\n"
    )

    # When: the source is analyzed after the try statement.
    violations = _source_checker()(source, "all_try_paths.py")

    # Then: no prohibited provenance remains possible.
    assert violations == ()


def test_source_checker_allows_rebinding_on_every_match_case() -> None:
    # Given: every match case rebinds a prohibited alias harmlessly.
    source = (
        "import subprocess as sp\n"
        "match value:\n"
        "    case 0:\n"
        "        import typing as sp\n"
        "    case _:\n"
        "        import typing as sp\n"
        "sp.run([])\n"
    )

    # When: the source is analyzed after all cases join.
    violations = _source_checker()(source, "all_match_cases.py")

    # Then: no prohibited provenance remains possible.
    assert violations == ()


def test_source_checker_skips_class_namespace_for_method_lookup() -> None:
    # Given: a module binding and a class-only rebinding with a method call.
    source = (
        "import typing as sp\n"
        "class C:\n"
        "    import subprocess as sp\n"
        "    def method(self):\n"
        "        sp.run([])\n"
    )

    # When: the source is analyzed across the method boundary.
    violations = _source_checker()(source, "class_method.py")

    # Then: the class namespace does not shadow the module binding in the method.
    assert violations == ()


def test_source_checker_detects_method_local_import() -> None:
    # Given: a method-local prohibited import.
    source = (
        "import typing as sp\n"
        "class C:\n"
        "    def method(self):\n"
        "        import subprocess as sp\n"
        "        sp.run([])\n"
    )

    # When: the source is analyzed within the method body.
    violations = _source_checker()(source, "method_local.py")

    # Then: the local prohibited provenance is reported.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


def test_source_checker_preserves_enclosing_function_closure_over_class_namespace() -> None:
    # Given: an enclosing function binding and a class-only harmless rebinding.
    source = (
        "def outer():\n"
        "    import subprocess as sp\n"
        "    class C:\n"
        "        import typing as sp\n"
        "        def method(self):\n"
        "            sp.run([])\n"
    )

    # When: the source is analyzed through the nested class and method boundaries.
    violations = _source_checker()(source, "function_closure.py")

    # Then: the enclosing function's prohibited closure remains visible to the method.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


def test_source_checker_uses_class_namespace_for_class_body_calls() -> None:
    # Given: a module binding and a class-body prohibited rebinding.
    source = "import typing as sp\nclass C:\n    import subprocess as sp\n    sp.run([])\n"

    # When: the source is analyzed while the class body executes.
    violations = _source_checker()(source, "class_body.py")

    # Then: the class namespace supplies the prohibited call provenance.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


def test_source_checker_separates_nested_class_and_method_namespaces() -> None:
    # Given: an outer class binding and no nested-class binding for the call sites.
    source = (
        "import typing as sp\n"
        "class Outer:\n"
        "    import subprocess as sp\n"
        "    class Inner:\n"
        "        sp.run([])\n"
        "        def method(self):\n"
        "            sp.run([])\n"
    )

    # When: the source is analyzed through both nested boundaries.
    violations = _source_checker()(source, "nested_class_method.py")

    # Then: neither nested class nor method captures the outer class namespace.
    assert violations == ()


def test_source_checker_evaluates_method_defaults_and_decorators_in_class_scope() -> None:
    # Given: class-scope prohibited provenance used only by definition-time expressions.
    source = (
        "import typing as sp\n"
        "class C:\n"
        "    import subprocess as sp\n"
        "    @sp.run([])\n"
        "    def method(self, value=sp.run([])):\n"
        "        sp.run([])\n"
    )

    # When: the source is analyzed across definition-time and method-body contexts.
    violations = _source_checker()(source, "method_definition_context.py")

    # Then: outer/class expressions are checked while the method body skips class locals.
    assert _codes(violations) == {"SUBPROCESS_RUN"}
