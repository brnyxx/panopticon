from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from panopticon.discovery.base import RawServerEntry, SourceLocation
from panopticon.engine.watch_inventory import WatchTargetContext
from panopticon.engine.watch_local_model import LocalWatchStatus
from panopticon.engine.watch_model import WatchOptions
from panopticon.engine.watch_remote_production import run_remote_production
from panopticon.inventory.normalize import normalize_entry
from panopticon.models import ConfigPath, ConfigScope, JsonPointer
from panopticon.models.ids import ClientName
from panopticon.models.state import StageStatus


class Resolver:
    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, host: str) -> tuple[str, ...]:
        self.calls += 1
        return ("93.184.216.34",)


def _context(tmp_path: Path) -> WatchTargetContext:
    path = tmp_path / "mcp.json"
    raw = RawServerEntry(
        "remote",
        {
            "url": "https://api.example.test/mcp?credential=removed",
            "headers": {"Authorization": "real-header-value"},
        },
        ConfigScope.GLOBAL,
        path,
        ConfigPath("~/mcp.json"),
        path,
        "a" * 64,
        JsonPointer("/mcpServers/remote"),
        SourceLocation(1, 1, 0),
    )
    installed = normalize_entry(raw, client=ClientName.GENERIC, home=str(tmp_path))
    return WatchTargetContext(installed, raw)


def _transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(204, request=request)
        payload = json.loads(request.content) if request.content else {}
        method = payload.get("method")
        identifier = payload.get("id")
        headers = {"Mcp-Session-Id": "session-secret", "Content-Type": "application/json"}
        result: Any
        if method == "initialize":
            result = {
                "protocolVersion": "2026-07-28",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "remote-fixture", "version": "1.0"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "read_data",
                        "description": "Read declared data",
                        "inputSchema": {"type": "object"},
                        "annotations": {"readOnlyHint": True},
                        "_meta": {
                            "panopticon": {
                                "complete": True,
                                "paths": [],
                                "hosts": ["api.example.test"],
                                "processes": [],
                            }
                        },
                    }
                ]
            }
        elif method == "tools/call":
            result = {"value": request.headers.get("Authorization", "")}
        else:
            return httpx.Response(202, headers=headers, request=request)
        body = {"jsonrpc": "2.0", "id": identifier, "result": result}
        return httpx.Response(200, headers=headers, json=body, request=request)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_remote_watch_uses_exact_requests_and_sanitizes_observation(tmp_path: Path) -> None:
    result = await run_remote_production(
        _context(tmp_path),
        WatchOptions(calls=1),
        resolver=Resolver(),
        transport=_transport(),
    )

    assert result.status is LocalWatchStatus.COMPLETE
    assert result.observation is not None
    observation = result.observation
    assert observation.sandbox.runtime == "remote"
    assert str(observation.sandbox.endpoint) == "https://api.example.test/mcp"
    kinds = {event.root.kind for span in observation.spans for event in span.events}
    assert {"net", "leak"} <= kinds
    assert observation.state.coverage.file.status is StageStatus.UNSUPPORTED
    assert observation.state.coverage.process.status is StageStatus.UNSUPPORTED
    rendered = observation.model_dump_json()
    assert "real-header-value" not in rendered
    assert "session-secret" not in rendered
    assert "credential=removed" not in rendered


@pytest.mark.asyncio
async def test_remote_offline_returns_before_resolution_or_http(tmp_path: Path) -> None:
    resolver = Resolver()

    result = await run_remote_production(
        _context(tmp_path),
        WatchOptions(offline=True),
        resolver=resolver,
        transport=_transport(),
    )

    assert result.status is LocalWatchStatus.UNSUPPORTED
    assert result.reason_code == "OFFLINE"
    assert resolver.calls == 0
