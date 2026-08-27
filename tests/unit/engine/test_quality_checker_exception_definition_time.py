"""Regression tests for definition-time exception alternatives."""

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

DEFINITION_TIME_RISK_CASES: Final[tuple[tuple[str, str], ...]] = (
    (
        "function_decorator",
        "import typing as sp\n"
        "try:\n"
        "    @make_decorator()\n"
        "    def deferred():\n"
        "        pass\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
    ),
    (
        "function_default",
        "import typing as sp\n"
        "try:\n"
        "    def deferred(value=make_default()):\n"
        "        pass\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
    ),
    (
        "evaluated_annotation",
        "import typing as sp\n"
        "try:\n"
        "    def deferred(value: make_annotation()):\n"
        "        pass\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
    ),
    (
        "class_base",
        "import typing as sp\n"
        "try:\n"
        "    class Deferred(make_base()):\n"
        "        pass\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
    ),
    (
        "class_decorator",
        "import typing as sp\n"
        "try:\n"
        "    @make_decorator()\n"
        "    class Deferred:\n"
        "        pass\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
    ),
    (
        "class_body",
        "import typing as sp\n"
        "try:\n"
        "    class Deferred:\n"
        "        make_value()\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
    ),
    (
        "direct_call",
        "import typing as sp\n"
        "try:\n"
        "    make_value()\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
    ),
    (
        "direct_import",
        "import typing as sp\n"
        "try:\n"
        "    import module_name\n"
        "except RuntimeError:\n"
        "    import subprocess as sp\n"
        "sp.run([])\n",
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


@pytest.mark.parametrize(("case", "source"), DEFINITION_TIME_RISK_CASES)
def test_source_checker_retains_definition_time_exception_alternatives(
    case: str,
    source: str,
) -> None:
    # Given: a definition-time expression that can raise while defining a construct.
    # When: the source is analyzed without executing it.
    violations = _source_checker()(source, f"definition_time_{case}.py")

    # Then: the handler alternative remains visible at the following call site.
    assert _codes(violations) == {"SUBPROCESS_RUN"}
