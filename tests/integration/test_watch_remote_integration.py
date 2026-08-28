"""Injected remote watch boundary coverage (no DNS or external network)."""

from __future__ import annotations

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


def _context(url: str = "https://api.example.test/mcp") -> WatchTargetContext:
    raw = RawServerEntry(
        "remote",
        {"url": url},
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
            body = {"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "fixture"}}}
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
    assert resolver.calls == 1


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
