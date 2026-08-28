"""Pure rendering projection for doctor data (no I/O)."""

from __future__ import annotations

from dataclasses import asdict

from panopticon.engine.doctor_model import DoctorData, DoctorOutcome


def doctor_mapping(data: DoctorData) -> dict[str, object]:
    """Return stable JSON-compatible values; alerts intentionally precede clients."""
    clients: list[dict[str, object]] = []
    for client in data.clients:
        groups: list[dict[str, object]] = []
        for group in client.groups:
            installations: list[dict[str, object]] = []
            for item in group.installations:
                value = asdict(item)
                normalized_history = item.history
                if normalized_history is not None:
                    dump = getattr(normalized_history, "model_dump", None)
                    value["history"] = dump(mode="json") if callable(dump) else None
                installations.append(value)
            groups.append({"server_id": group.server_id, "installations": installations})
        clients.append({"name": client.name, "status": client.status, "groups": groups})
    matches = [
        {
            "rule_id": match.rule_id,
            "severity": match.severity.value,
            "kind": match.kind.value,
            "fix_id": match.fix_id,
            "server_id": match.server_id,
            "installation_id": match.installation_id,
            "evidence": [
                {
                    "subject": item.subject,
                    "classification": item.classification,
                }
                for item in match.evidence
            ],
        }
        for match in data.config_matches
    ]
    history_records = [
        {
            "installation_id": item.installation_id,
            "outcomes": [
                {
                    "rule_id": outcome.rule_id,
                    "status": outcome.status.value,
                    "severity": outcome.severity.value,
                    "kind": outcome.kind.value,
                    "reason": outcome.reason,
                    "evidence": [
                        {
                            "subject": evidence.subject,
                            "classification": evidence.classification,
                        }
                        for evidence in outcome.evidence
                    ],
                }
                for outcome in item.outcomes
            ],
        }
        for item in data.history_outcomes
    ]
    return {
        "alerts": list(data.alerts),
        "clients": clients,
        "config_matches": matches,
        "history_outcomes": history_records,
    }


def render_outcome(outcome: DoctorOutcome) -> dict[str, object]:
    """Render status metadata alongside sanitized doctor values."""
    result = outcome.result
    coverage = {
        name: {
            "status": stage.status.value,
            "reason_code": stage.reason_code.value,
            "diagnostics": [{"code": d.code, "detail": d.detail} for d in stage.diagnostics],
        }
        for name, stage in (
            ("file", result.coverage.file),
            ("net", result.coverage.net),
            ("process", result.coverage.process),
            ("dns", result.coverage.dns),
            ("proxy", result.coverage.proxy),
            ("snapshot", result.coverage.snapshot),
            ("stdio", result.coverage.stdio),
        )
    }
    return {
        "status": result.status.value,
        "reason_code": result.reason_code.value,
        "coverage": coverage,
        "diagnostics": [{"code": d.code, "detail": d.detail} for d in result.diagnostics],
        "doctor": doctor_mapping(outcome.data),
    }


__all__ = ["doctor_mapping", "render_outcome"]
