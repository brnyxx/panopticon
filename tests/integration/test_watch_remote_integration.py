"""Injected remote watch boundary coverage (no DNS or external network)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from panopticon.discovery.base import RawServerEntry, SourceLocation
from panopticon.engine.watch_inventory import WatchTargetContext
from panopticon.engine.watch_model import WatchOptions
from panopticon.engine.watch_remote_production import run_remote_production
from panopticon.inventory.normalize import normalize_entry
from panopticon.models.ids import ClientName, ConfigPath, ConfigScope, JsonPointer
from panopticon.probe.remote_security import Resolver


class _Resolver(Resolver):
    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, host: str) -> tuple[str, ...]:
        self.calls += 1
        return ("93.184.216.34",)


def _context(
    url: str = "https://api.example.test/mcp",
    *,
    transport: str | None = None,
) -> WatchTargetContext:
    entry: dict[str, object] = {"url": url}
    if transport is not None:
        entry["type"] = transport
    raw = RawServerEntry(
        "remote",
        entry,
        ConfigScope.PROJECT,
        Path("config.json"),
        ConfigPath("~/config.json"),
        Path("config.json"),
        "0" * 64,
        JsonPointer("/remote"),
        SourceLocation(1, 1, 0),
    )
    return WatchTargetContext(normalize_entry(raw, client=ClientName.GENERIC, home="/tmp"), raw)


@pytest.mark.asyncio
async def test_remote_watch_uses_injected_transport_and_resolver() -> None:
    requests: list[str] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        payload = request.content.decode()
        if '"initialize"' in payload:
            body = {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": "2026-07-28",
                    "serverInfo": {"name": "fixture"},
                },
            }
        elif '"tools/list"' in payload:
            body = {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}
        else:
            body = {"jsonrpc": "2.0", "id": 3, "result": {}}
        return httpx.Response(200, json=body, headers={"Mcp-Session-Id": "s"})

    resolver = _Resolver()
    result = await run_remote_production(
        _context(),
        WatchOptions(calls=0, timeout=1),
        resolver=resolver,
        transport=httpx.MockTransport(respond),
    )
    assert result.status.value == "COMPLETE"
    assert requests[:2] == ["/mcp", "/mcp"]
    assert resolver.calls >= 2


@pytest.mark.asyncio
async def test_remote_offline_skips_resolution_and_transport() -> None:
    resolver = _Resolver()
    result = await run_remote_production(
        _context(),
        WatchOptions(offline=True),
        resolver=resolver,
        transport=httpx.MockTransport(lambda request: pytest.fail("network used")),
    )
    assert result.reason_code == "OFFLINE"
    assert resolver.calls == 0


@pytest.mark.asyncio
async def test_remote_deprecated_sse_fallback_is_observed() -> None:
    requests: list[tuple[str, str]] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(
                200,
                text="event: endpoint\ndata: /messages\n\n",
                headers={"content-type": "text/event-stream"},
            )
        if request.url.path == "/sse":
            return httpx.Response(405)
        payload = json.loads(request.content)
        if "id" not in payload:
            return httpx.Response(204)
        method = payload["method"]
        result: object = (
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "legacy", "version": "1"},
            }
            if method == "initialize"
            else {"tools": []}
            if method == "tools/list"
            else {}
        )
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": result},
        )

    result = await run_remote_production(
        _context("https://api.example.test/sse", transport="sse"),
        WatchOptions(calls=0, timeout=1),
        resolver=_Resolver(),
        transport=httpx.MockTransport(respond),
    )

    assert result.status.value == "COMPLETE"
    assert result.observation is not None
    assert ("GET", "/sse") in requests
    assert ("POST", "/messages") in requests
    assert result.observation.protocol.era.value == "legacy"
    assert result.observation.protocol.fallback_reason.value == "LEGACY_REQUIRED"
    assert result.observation.protocol.selected_version == "2024-11-05"
