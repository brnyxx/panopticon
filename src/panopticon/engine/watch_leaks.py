"""Detect exact synthetic marker exposure without persisting marker values."""

from __future__ import annotations

import ast
import json
from collections import Counter

from panopticon.models.event import Event, LeakEvent
from panopticon.sandbox.matcher import DecoyMatcher

from .watch_local_model import LocalWatchResult


def leak_events_by_span(result: LocalWatchResult) -> dict[str, tuple[Event, ...]]:
    manifest = result.manifest
    if manifest is None:
        return {}
    startup = next((span.span_id for span in result.spans if span.kind.value == "startup"), None)
    output: dict[str, Counter[tuple[str, str]]] = {}

    def inspect(span_id: str | None, sink: str, payload: bytes) -> None:
        if span_id is None:
            return
        report = DecoyMatcher(manifest).match((payload,))
        counts = output.setdefault(span_id, Counter())
        for match in report.matches:
            counts[(match.key, sink)] += 1

    if result.stderr is not None:
        inspect(startup, "stderr", result.stderr.data)
    for notification in result.notifications:
        inspect(startup, "notification", json.dumps(notification, sort_keys=True).encode())
    if result.calls is not None:
        for call in result.calls.calls:
            if call.response is None:
                continue
            span_id = next(
                (
                    span.span_id
                    for span in result.spans
                    if span.tool == call.tool and span.call_index == call.call_index
                ),
                None,
            )
            inspect(span_id, "response", json.dumps(call.response.result, sort_keys=True).encode())
    for event in result.trace.events if result.trace is not None else ():
        if event.operation != "exec" or len(event.arguments) < 2:
            continue
        span_id = next(
            (
                span.span_id
                for span in result.spans
                if span.kind.value == "call"
                and span.started_at.timestamp() <= event.timestamp <= span.ended_at.timestamp()
            ),
            startup,
        )
        try:
            payload = ast.literal_eval(event.arguments[1])
        except (SyntaxError, ValueError):
            continue
        if isinstance(payload, str):
            inspect(span_id, "exec_arg", payload.encode())
    return {
        span_id: tuple(
            Event(
                LeakEvent(
                    schema_version="1.0",
                    kind="leak",
                    op="expose",
                    decoy_key=key,
                    sink=sink,
                    count=count,
                )
            )
            for (key, sink), count in sorted(counts.items())
        )
        for span_id, counts in output.items()
    }


__all__ = ["leak_events_by_span"]
