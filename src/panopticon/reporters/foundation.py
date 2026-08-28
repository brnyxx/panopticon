"""Foundation engine-result adapter into sanitized reporters."""

from __future__ import annotations

from dataclasses import replace

from panopticon.engine.contracts import Result
from panopticon.engine.exit_codes import NOT_IMPLEMENTED_EXIT, result_exit_code
from panopticon.reporters.base import Render
from panopticon.reporters.json import JsonReporter
from panopticon.reporters.model import from_result
from panopticon.reporters.terminal import TerminalReporter


def _is_stub(result: Result) -> bool:
    return any(diagnostic.code == "NOT_IMPLEMENTED" for diagnostic in result.diagnostics)


def render(result: Result, *, json_output: bool) -> Render:
    try:
        model = from_result(result)
    except ValueError:
        return Render(stdout="", stderr="", exit_code=1)
    stub = _is_stub(result)
    exit_code = NOT_IMPLEMENTED_EXIT if stub else result_exit_code(result)
    reporter = (
        JsonReporter(exit_code=exit_code) if json_output else TerminalReporter(exit_code=exit_code)
    )
    output = reporter.render(model)
    return replace(output, stderr="NOT_IMPLEMENTED\n") if stub else output


__all__ = ["render"]
