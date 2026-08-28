"""Deterministic dry-run and outcome rendering for install transactions."""

from __future__ import annotations

from dataclasses import dataclass

from panopticon.fix.plan import apply_bytes, unified_diff
from panopticon.install.model import InstallBatchOutcome


@dataclass(frozen=True, slots=True)
class RenderedInstall:
    stdout: str
    stderr: str
    exit_code: int


def render(outcome: InstallBatchOutcome) -> RenderedInstall:
    lines: list[str] = []
    for item in outcome.outcomes:
        if item.plan is not None:
            lines.append(
                unified_diff(
                    item.plan.fix_plan,
                    apply_bytes(item.plan.fix_plan),
                ).rstrip("\n")
            )
        line = f"{item.server_name}: {item.status.value} ({item.reason_code})"
        if item.transaction_id is not None:
            line += f" transaction={item.transaction_id}"
        lines.append(line)
    text = "\n".join(lines)
    if text:
        text += "\n"
    return RenderedInstall(text, "", 0 if outcome.successful else 4)


__all__ = ["RenderedInstall", "render"]
