"""Focused tests for the deterministic source-quality checker seam."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final, Literal, assert_never

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
quality_checker = importlib.import_module("check_no_excuse_rules")


def _source_checker() -> Callable[[str, str], tuple[str, ...]]:
    """Load the in-memory checker seam without making collection depend on it."""
    checker: Callable[[str, str], tuple[str, ...]] | None = getattr(
        quality_checker, "violations_from_source", None
    )
    assert checker is not None and callable(checker), "source quality checker is missing"
    return checker


def _codes(violations: tuple[str, ...]) -> frozenset[str]:
    """Extract machine issue codes from checker results."""
    return frozenset(item.rsplit(":", maxsplit=1)[-1] for item in violations)


def test_source_checker_catches_waits_runs_and_suppressions() -> None:
    # Given: source using canonical waits, subprocess execution, and suppression markers.
    noqa = "# " + "no" + "qa"
    type_ignore = "# " + "type:" + " " + "ignore"
    pyright_ignore = "# " + "pyright:" + " " + "ignore"
    source = "\n".join(
        (
            "import asyncio",
            "import subprocess",
            "import time",
            "time.sleep(1)",
            "asyncio.sleep(1)",
            'subprocess.run(["command"])',
            noqa,
            type_ignore,
            pyright_ignore,
        )
    )

    # When: the source is analyzed without creating a file.
    violations = _source_checker()(source, "bad.py")

    # Then: each prohibited construct has a deterministic machine code.
    assert {
        "TIME_SLEEP",
        "ASYNCIO_SLEEP",
        "SUBPROCESS_RUN",
        "SUPPRESSION",
    } <= _codes(violations)


def test_source_checker_resolves_local_aliases_for_prohibited_calls() -> None:
    # Given: aliases and direct imports for each prohibited call family.
    source = "\n".join(
        (
            "import asyncio as aio",
            "import subprocess as proc",
            "import time as clock",
            "from asyncio import sleep as pause",
            "from subprocess import run as execute",
            "from time import sleep as nap",
            "clock.sleep(1)",
            "aio.sleep(1)",
            'proc.run(["command"])',
            "pause(1)",
            'execute(["command"])',
            "nap(1)",
        )
    )

    # When: the source is analyzed without resolving imports outside this module.
    violations = _source_checker()(source, "aliases.py")

    # Then: local aliases and direct-import bindings retain the same machine codes.
    assert {"TIME_SLEEP", "ASYNCIO_SLEEP", "SUBPROCESS_RUN"} <= _codes(violations)


def test_source_checker_preserves_earlier_call_before_top_level_rebind() -> None:
    # Given: a prohibited aliased call followed by a harmless top-level rebind.
    source = "import subprocess as sp\nsp.run([])\nimport typing as sp\n"

    # When: the source is analyzed in source order.
    violations = _source_checker()(source, "top_level_rebind.py")

    # Then: the earlier call keeps its stable prohibited-call finding.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


def test_source_checker_keeps_outer_binding_through_nested_shadow() -> None:
    # Given: an inner harmless import shadows an outer prohibited module alias.
    source = "\n".join(
        (
            "import subprocess as process_module",
            "def inner() -> None:",
            "    import typing as process_module",
            "    process_module.run([])",
            "process_module.run([])",
        )
    )

    # When: the nested source is analyzed with lexical scopes.
    violations = _source_checker()(source, "nested_shadow.py")

    # Then: only the outer call retains the prohibited module provenance.
    assert _codes(violations) == {"SUBPROCESS_RUN"}


def test_source_checker_respects_function_local_rebind_order() -> None:
    # Given: calls before import/assignment rebinds and a call after an assignment rebind.
    source = "\n".join(
        (
            "def call_before_assignment_rebind() -> None:",
            "    import time as clock",
            "    clock.sleep(1)",
            "    clock = object()",
            "def call_before_import_rebind() -> None:",
            "    import subprocess as process_module",
            "    process_module.run([])",
            "    import typing as process_module",
            "def call_after_assignment_rebind() -> None:",
            "    import os as operating_system",
            "    operating_system = object()",
            "    operating_system.system([])",
        )
    )

    # When: each function-local statement stream is analyzed in source order.
    violations = _source_checker()(source, "function_rebind.py")

    # Then: only calls before their respective rebinds retain provenance.
    assert _codes(violations) == {"TIME_SLEEP", "SUBPROCESS_RUN"}


def test_source_checker_detects_function_aliases_not_ordinary_call_names() -> None:
    # Given: function-local prohibited aliases and unrelated functions named run/system.
    source = "\n".join(
        (
            "def run() -> None:",
            "    pass",
            "def system() -> None:",
            "    pass",
            "run()",
            "system()",
            "def prohibited() -> None:",
            "    import subprocess",
            "    import subprocess as process_module",
            "    from subprocess import run as execute",
            "    import os as operating_system",
            "    from time import sleep as pause",
            "    subprocess.run([])",
            "    process_module.run([])",
            "    execute([])",
            "    operating_system.system([])",
            "    pause(1)",
        )
    )

    # When: the source is analyzed without executing any function.
    violations = _source_checker()(source, "function_aliases.py")

    # Then: independent canonical, module-alias, and direct-import calls remain detected.
    assert _codes(violations) == {"SUBPROCESS_RUN", "OS_SYSTEM", "TIME_SLEEP"}


PROCESS_API_CASES: Final = (
    ("subprocess", "run", "SUBPROCESS_RUN"),
    ("subprocess", "call", "SUBPROCESS_CALL"),
    ("subprocess", "check_call", "SUBPROCESS_CHECK_CALL"),
    ("subprocess", "check_output", "SUBPROCESS_CHECK_OUTPUT"),
    ("subprocess", "Popen", "SUBPROCESS_POPEN"),
    ("os", "system", "OS_SYSTEM"),
)
PROCESS_CALL_FORMS: Final = ("canonical", "module-alias", "direct-import-alias")


@pytest.mark.parametrize(("module", "function", "expected_code"), PROCESS_API_CASES)
@pytest.mark.parametrize("form", PROCESS_CALL_FORMS)
def test_source_checker_rejects_required_process_api_provenance_forms(
    module: str,
    function: str,
    expected_code: str,
    form: Literal["canonical", "module-alias", "direct-import-alias"],
) -> None:
    # Given: one prohibited synchronous process API through one supported import form.
    match form:
        case "canonical":
            source = f"import {module}\n{module}.{function}(None)\n"
        case "module-alias":
            source = f"import {module} as imported_module\nimported_module.{function}(None)\n"
        case "direct-import-alias":
            source = f"from {module} import {function} as imported_call\nimported_call(None)\n"
        case unreachable:
            assert_never(unreachable)

    # When: the AST/provenance checker analyzes the source.
    violations = _source_checker()(source, f"{module}_{function}_{form}.py")

    # Then: exactly the stable machine code for that prohibited API is emitted.
    assert _codes(violations) == {expected_code}


def test_source_checker_allows_network_stdio_and_async_process_controls() -> None:
    # Given: network, stdio, event-based async, and the approved async process primitive.
    source = "\n".join(
        (
            "import asyncio",
            "import socket",
            "import sys",
            "def run() -> None:",
            "    pass",
            "def system() -> None:",
            "    pass",
            "run()",
            "system()",
            "async def observe() -> None:",
            "    event = asyncio.Event()",
            "    await event.wait()",
            "    process = await asyncio.create_subprocess_exec(",
            '        "command",',
            "        stdout=asyncio.subprocess.PIPE,",
            "    )",
            '    sys.stdout.write("ready")',
            '    socket.create_connection(("localhost", 80))',
        )
    )

    # When: the source is analyzed without executing its operations.
    violations = _source_checker()(source, "approved_controls.py")

    # Then: only explicitly prohibited synchronous APIs are rejected.
    assert violations == ()


@pytest.mark.parametrize(
    "source",
    (
        "import asyncio\nimport subprocess\nimport time\n",
        "from asyncio import Event\n\n"
        "async def wait_for_state(event: Event) -> None:\n"
        "    await event.wait()\n",
    ),
)
def test_source_checker_allows_imports_and_event_based_async_code(source: str) -> None:
    # When: ordinary imports or state-based waiting are analyzed.
    violations = _source_checker()(source, "good.py")

    # Then: no time-based shortcut or prohibited process execution is reported.
    assert violations == ()
