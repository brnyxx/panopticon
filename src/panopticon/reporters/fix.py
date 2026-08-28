"""Deterministic terminal rendering for fix command results."""

from __future__ import annotations

from dataclasses import dataclass

from panopticon.engine.fix import FixCommandResult


@dataclass(frozen=True, slots=True)
class RenderedFix:
    stdout: str
    stderr: str
    exit_code: int


def render(result: FixCommandResult) -> RenderedFix:
    lines: list[str] = []
    for diff in result.diffs:
        lines.append(diff.rstrip("\n"))
    for outcome in result.batch.outcomes:
        line = f"{outcome.fix_id} {outcome.status.value} {outcome.reason_code}"
        if outcome.transaction_id is not None:
            line += f" transaction={outcome.transaction_id}"
        lines.append(line)
    text = "\n".join(lines)
    if text:
        text += "\n"
    if result.exit_code == 0:
        return RenderedFix(text, "", 0)
    return RenderedFix("", text or "FIX_CONFIG_UNAVAILABLE\n", result.exit_code)


__all__ = ["RenderedFix", "render"]
