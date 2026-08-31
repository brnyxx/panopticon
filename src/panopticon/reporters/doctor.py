"""Sanitized deterministic doctor output."""

from __future__ import annotations

import json

from panopticon.engine.doctor_model import DoctorOutcome
from panopticon.engine.doctor_render import render_outcome
from panopticon.engine.exit_codes import result_exit_code
from panopticon.i18n.messages import message
from panopticon.reporters.base import Render


def render(
    outcome: DoctorOutcome,
    *,
    json_output: bool = False,
    locale: str | None = None,
) -> Render:
    payload = render_outcome(outcome)
    code = result_exit_code(outcome.result)
    if outcome.result.status.value == "PARTIAL":
        code = 3
    if json_output:
        return Render(
            stdout=json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            stderr="",
            exit_code=code,
        )

    lines: list[str] = []
    for alert in outcome.data.alerts:
        lines.append(f"ALERT: {alert}")
    for match in outcome.data.config_matches:
        lines.append(f"{match.rule_id} {match.severity.value} {match.installation_id}")
    for history in outcome.data.history_outcomes:
        for history_outcome in history.outcomes:
            if history_outcome.status.value != "clear":
                lines.append(
                    f"{history_outcome.rule_id} {history_outcome.status.value.upper()} "
                    f"{history.installation_id} {history_outcome.reason}"
                )
    for client in outcome.data.clients:
        lines.append(f"{client.name}: {client.status}")
        for group in client.groups:
            lines.append(f"  {group.server_id}:")
            for installation in group.installations:
                lines.append(
                    f"    {installation.name} [{installation.transport}] ({installation.scope})"
                )
                if installation.command:
                    lines.append(f"      command: {installation.command}")
                if installation.url:
                    lines.append(f"      url: {installation.url}")
                if installation.env_keys:
                    lines.append(f"      env_keys: {', '.join(installation.env_keys)}")
                if installation.headers_keys:
                    lines.append(f"      headers_keys: {', '.join(installation.headers_keys)}")
                if installation.history is not None:
                    lines.append(f"      history: {installation.history.status.value}")
    lines.append(f"Status: {outcome.result.status.value}")
    lines.append(f"Reason: {outcome.result.reason_code.value}")
    if outcome.result.diagnostics:
        lines.append(
            "Diagnostics: "
            + ", ".join(diagnostic.code for diagnostic in outcome.result.diagnostics)
        )
    # Guidance is additive and deliberately does not derive a new verdict from coverage.
    lines.append(message("next_command", locale=locale))
    return Render(stdout="\n".join(lines) + "\n", stderr="", exit_code=code)


__all__ = ["render"]
