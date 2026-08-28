"""Event-driven call-driver success and failure states."""

from __future__ import annotations

import asyncio

import pytest

from panopticon.probe.client import ProbeResult, ProbeStatus
from panopticon.probe.driver import (
    CallDriver,
    CallStatus,
    DriverStatus,
    parse_overrides,
    run_calls,
)


class FakeClient:
    def __init__(self, listed=None, responses=None, gate: asyncio.Event | None = None):
        self.listed = listed
        self.responses = list(responses or [])
        self.gate = gate
        self.requests: list[tuple[str, dict, float | None]] = []
        self.request_event = asyncio.Event()

    async def list_paginated(self, method, *, timeout=None):
        self.requests.append((method, {}, timeout))
        if self.listed is None:
            return ProbeResult(ProbeStatus.COMPLETE, "OK", {"tools": []})
        return ProbeResult(ProbeStatus.COMPLETE, "OK", {"tools": self.listed})

    async def request(self, method, params=None, *, timeout=None):
        self.requests.append((method, params or {}, timeout))
        self.request_event.set()
        if self.gate is not None:
            await self.gate.wait()
        return (
            self.responses.pop(0) if self.responses else ProbeResult(ProbeStatus.COMPLETE, "OK", {})
        )


@pytest.mark.asyncio
async def test_zero_tools_and_zero_calls_are_complete_without_call_requests() -> None:
    client = FakeClient()
    result = await CallDriver(client, calls=2).run()
    assert result == (await CallDriver(FakeClient([{"name": "x"}]), calls=0).run())
    assert result.status is DriverStatus.COMPLETE and result.reason_code == "ZERO_TOOLS"
    assert not any(x[0] == "tools/call" for x in client.requests)


@pytest.mark.asyncio
async def test_multi_tool_calls_are_stable_and_metadata_is_generated() -> None:
    tools = [
        {
            "name": "z",
            "inputSchema": {"type": "object", "required": ["x"], "properties": {"x": {"const": 1}}},
        },
        {"name": "a", "inputSchema": {"type": "object"}},
    ]
    client = FakeClient(tools)
    result = await run_calls(client, tools, calls=2, seed="fixed")
    assert result.status is DriverStatus.COMPLETE
    calls = [p for p in client.requests if p[0] == "tools/call"]
    assert [p[1]["name"] for p in calls] == ["a", "z", "a", "z"]
    assert calls[1][1]["arguments"] == {"x": 1}


@pytest.mark.asyncio
async def test_failed_call_yields_partial_and_unsupported_schema_is_recorded() -> None:
    tools = [
        {"name": "bad", "inputSchema": {"allOf": [{"const": 1}, {"const": 2}]}},
        {"name": "ok"},
    ]
    client = FakeClient(tools, [ProbeResult(ProbeStatus.ERROR, "SERVER_ERROR")])
    result = await run_calls(client, tools)
    assert result.status is DriverStatus.PARTIAL
    assert [x.reason_code for x in result.calls] == [
        "UNSATISFIABLE_SCHEMA",
        "SERVER_ERROR",
    ]
    assert result.calls[0].status is CallStatus.UNPROBEABLE


@pytest.mark.asyncio
async def test_cancellation_is_event_driven_and_does_not_leave_driver_task() -> None:
    gate = asyncio.Event()
    client = FakeClient([{"name": "slow"}], gate=gate)
    driver = CallDriver(client, calls=3)
    task = asyncio.create_task(driver.run())
    await client.request_event.wait()
    cancelled = await driver.cancel()
    result = await task
    assert cancelled.status is DriverStatus.CANCELLED
    assert result.status is DriverStatus.CANCELLED


@pytest.mark.asyncio
async def test_overrides_are_passed_verbatim_and_list_failure_is_incomplete() -> None:
    client = FakeClient([{"name": "x"}], [ProbeResult(ProbeStatus.COMPLETE, "OK", {"ok": True})])
    result = await CallDriver(client, calls=1).run(overrides={"x": {"danger": False}})
    assert result.status is DriverStatus.COMPLETE
    assert client.requests[-1][1]["arguments"] == {"danger": False}

    class ListFailure(FakeClient):
        async def list_paginated(self, method, *, timeout=None):
            return ProbeResult(ProbeStatus.INCOMPLETE, "TIMEOUT")

    failed = await CallDriver(ListFailure()).run()
    assert failed.status is DriverStatus.INCOMPLETE
    assert failed.reason_code == "TIMEOUT"


@pytest.mark.asyncio
async def test_real_env_destructive_calls_are_skipped_and_partial() -> None:
    tools = [
        {"name": "delete_everything", "inputSchema": {"type": "object"}},
        {"name": "read_data", "inputSchema": {"type": "object"}},
    ]
    client = FakeClient(tools)

    result = await CallDriver(client, real_env=True).run(tools)

    assert result.status is DriverStatus.PARTIAL
    assert [outcome.reason_code for outcome in result.calls] == [
        "SKIPPED_DESTRUCTIVE",
        "OK",
    ]
    assert [request[1]["name"] for request in client.requests] == ["read_data"]


def test_manual_overrides_parse_only_json_object_values() -> None:
    assert parse_overrides('{"tool":{"count":2,"enabled":true}}') == {
        "tool": {"count": 2, "enabled": True}
    }
    with pytest.raises(ValueError):
        parse_overrides("[]")
