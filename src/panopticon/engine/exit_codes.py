"""One deterministic exit-code policy for engine results and CLI boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from panopticon.engine.contracts import FailedResult, IncompleteResult, Result, UnsupportedResult

NOT_IMPLEMENTED_EXIT: Final = 64


@dataclass(frozen=True, slots=True)
class ExitInputs:
    """Independent machine signals consumed by the single exit policy."""

    policy_finding: bool = False
    incomplete_required_coverage: bool = False
    runtime_failure: bool = False
    config_failure: bool = False
    usage_error: bool = False


def resolve_exit_code(inputs: ExitInputs) -> int:
    """Resolve the explicit precedence: usage, config, runtime, incomplete, policy, success."""
    if inputs.usage_error:
        return 2
    if inputs.config_failure:
        return 4
    if inputs.runtime_failure:
        return 5
    if inputs.incomplete_required_coverage:
        return 3
    if inputs.policy_finding:
        return 1
    return 0


def result_exit_code(result: Result) -> int:
    """Map a typed result to the same policy without reinterpreting it in the CLI."""
    inputs = ExitInputs(
        incomplete_required_coverage=isinstance(result, IncompleteResult),
        runtime_failure=isinstance(result, (FailedResult, UnsupportedResult)),
    )
    return resolve_exit_code(inputs)


__all__ = ["NOT_IMPLEMENTED_EXIT", "ExitInputs", "resolve_exit_code", "result_exit_code"]
