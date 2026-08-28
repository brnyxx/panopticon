"""Deterministic install outcome rendering."""

from __future__ import annotations

from panopticon.install.model import InstallBatchOutcome


def render_install(outcome: InstallBatchOutcome) -> str:
    lines = [f"{item.server_name}: {item.status} ({item.reason_code})" for item in outcome.outcomes]
    return "\n".join(lines)


def render(outcome: InstallBatchOutcome) -> str:
    return render_install(outcome)


__all__ = ["render", "render_install"]
