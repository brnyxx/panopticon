"""Small sanitized JSON/text renderer used until the reporter epic lands."""

from __future__ import annotations

import json

from panopticon.engine.contracts import Result
from panopticon.engine.exit_codes import NOT_IMPLEMENTED_EXIT, result_exit_code
from panopticon.reporters.base import Render


def _payload(result: Result) -> dict[str, object]:
    diagnostics = tuple(
        {"code": diagnostic.code, "detail": diagnostic.code} for diagnostic in result.diagnostics
    )
    return {
        "classification": result.status.value,
        "diagnostics": diagnostics,
        "reason_code": result.reason_code.value,
        "status": result.status.value,
    }


def _is_stub(result: Result) -> bool:
    return any(diagnostic.code == "NOT_IMPLEMENTED" for diagnostic in result.diagnostics)


def render(result: Result, *, json_output: bool) -> Render:
    payload = _payload(result)
    if json_output:
        stdout = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        stdout += "\n"
    else:
        stdout = f"{payload['status']} {payload['reason_code']}\n"
    stub = _is_stub(result)
    stderr = "NOT_IMPLEMENTED\n" if stub else ""
    exit_code = NOT_IMPLEMENTED_EXIT if stub else result_exit_code(result)
    return Render(stdout=stdout, stderr=stderr, exit_code=exit_code)


__all__ = ["render"]
