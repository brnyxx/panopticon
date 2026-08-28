"""Shared bounded MCP capability pagination."""

from __future__ import annotations

from typing import Protocol

from .argument_schema import JsonValue
from .protocol import ProbeResult, ProbeStatus


class PageClient(Protocol):
    async def request(
        self,
        method: str,
        params: dict[str, JsonValue] | None = None,
        *,
        timeout: float | None = None,
    ) -> ProbeResult: ...


async def list_paginated(
    client: PageClient,
    capabilities: dict[str, JsonValue],
    method: str,
    *,
    timeout: float | None = None,
) -> ProbeResult:
    capability = method.partition("/")[0]
    if capability not in capabilities:
        return ProbeResult(ProbeStatus.UNSUPPORTED, "CAPABILITY_UNSUPPORTED")
    output: list[JsonValue] = []
    cursor: str | None = None
    seen: set[str] = set()
    while True:
        result = await client.request(
            method,
            {} if cursor is None else {"cursor": cursor},
            timeout=timeout,
        )
        if result.status is not ProbeStatus.COMPLETE:
            return result
        if not isinstance(result.result, dict):
            return ProbeResult(ProbeStatus.ERROR, "MALFORMED_RESPONSE")
        values = result.result.get(capability, [])
        if not isinstance(values, list):
            return ProbeResult(ProbeStatus.ERROR, "MALFORMED_RESPONSE")
        output.extend(values)
        next_cursor = result.result.get("nextCursor")
        if next_cursor is None:
            return ProbeResult(ProbeStatus.COMPLETE, "OK", {capability: output})
        if not isinstance(next_cursor, str):
            return ProbeResult(ProbeStatus.ERROR, "MALFORMED_RESPONSE")
        if next_cursor in seen:
            return ProbeResult(ProbeStatus.ERROR, "DUPLICATE_CURSOR")
        seen.add(next_cursor)
        cursor = next_cursor


__all__ = ["list_paginated"]
