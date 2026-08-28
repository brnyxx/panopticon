"""CI scan policy with persistence-before-exit precedence."""

from __future__ import annotations

from enum import StrEnum

from panopticon.engine.contracts import EngineStatus
from panopticon.engine.scan import ScanOutcome


class FailOn(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    INCOMPLETE = "incomplete"
    NEVER = "never"


_SEVERITY = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0, "INFO": 0}


def ci_exit_code(
    outcome: ScanOutcome,
    fail_on: FailOn,
    *,
    sarif_persisted: bool,
) -> int:
    """Resolve runtime/config, required coverage, policy, then success."""
    if not sarif_persisted:
        return 4
    if outcome.status is EngineStatus.FAILED:
        return 4
    if outcome.status in {EngineStatus.INCOMPLETE, EngineStatus.UNSUPPORTED}:
        return 3
    if fail_on in {FailOn.NEVER, FailOn.INCOMPLETE}:
        return 0
    threshold = 2 if fail_on is FailOn.HIGH else 1
    return (
        1
        if any(
            _SEVERITY.get(finding.severity.upper(), 0) >= threshold for finding in outcome.findings
        )
        else 0
    )


__all__ = ["FailOn", "ci_exit_code"]
