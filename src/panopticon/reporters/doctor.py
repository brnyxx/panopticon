"""Sanitized deterministic doctor output."""

from __future__ import annotations

import json

from panopticon.engine.doctor_model import DoctorOutcome
from panopticon.engine.doctor_render import render_outcome
from panopticon.engine.exit_codes import result_exit_code
from panopticon.reporters.base import Render


def render(outcome: DoctorOutcome, *, json_output: bool = False) -> Render:
    payload = render_outcome(outcome)
    code = result_exit_code(outcome.result)
    if json_output:
        return Render(
            stdout=json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            stderr="",
            exit_code=code,
        )

    doctor = payload["doctor"]
    lines: list[str] = []
    alerts = doctor["alerts"]
    for alert in alerts:
        lines.append(f"ALERT: {alert}")
    for client in doctor["clients"]:
        lines.append(f"{client['name']}: {client['status']}")
        for group in client["groups"]:
            lines.append(f"  {group['server_id']}:")
            for item in group["installations"]:
                lines.append(f"    {item['name']} [{item['transport']}] ({item['scope']})")
                if item.get("command"):
                    lines.append(f"      command: {item['command']}")
                if item.get("url"):
                    lines.append(f"      url: {item['url']}")
                if item.get("env_keys"):
                    lines.append(f"      env_keys: {', '.join(item['env_keys'])}")
                if item.get("headers_keys"):
                    lines.append(f"      headers_keys: {', '.join(item['headers_keys'])}")
                if item.get("history") is not None:
                    history = item["history"]
                    lines.append(f"      history: {history.get('status', 'UNKNOWN')}")
    lines.append(f"Status: {payload['status']}")
    lines.append(f"Reason: {payload['reason_code']}")
    diagnostics = payload["diagnostics"]
    if diagnostics:
        lines.append("Diagnostics: " + ", ".join(d["code"] for d in diagnostics))
    return Render(stdout="\n".join(lines) + "\n", stderr="", exit_code=code)


__all__ = ["render"]
