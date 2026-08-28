"""Stable rendering for typed rule explanations."""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import JsonValue

from panopticon.engine.explain import ExplainResult, ExplainStatus


@dataclass(frozen=True, slots=True)
class RenderedExplain:
    stdout: str
    stderr: str
    exit_code: int


def render_explanation(result: ExplainResult) -> str:
    if result.document is None:
        return f"{result.rule_id}: {result.status.value} ({result.reason_code})"
    body = [f"# {result.rule_id}", ""]
    for section in result.document.sections:
        body.extend((f"## {section.section_id}", section.body, ""))
    return "\n".join(body).rstrip()


def render_explanation_json(result: ExplainResult) -> str:
    payload: dict[str, JsonValue] = {
        "reason_code": result.reason_code,
        "rule_id": result.rule_id,
        "status": result.status.value,
    }
    if result.document is not None:
        payload["locale"] = result.document.locale
        payload["sections"] = {
            section.section_id: section.body for section in result.document.sections
        }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def render(result: ExplainResult, *, json_output: bool = False) -> RenderedExplain:
    text = (render_explanation_json(result) if json_output else render_explanation(result)) + "\n"
    if result.status is ExplainStatus.KNOWN:
        return RenderedExplain(text, "", 0)
    exit_code = 4 if result.status is ExplainStatus.UNKNOWN else 3
    return RenderedExplain("", text, exit_code)


__all__ = [
    "RenderedExplain",
    "render",
    "render_explanation",
    "render_explanation_json",
]
