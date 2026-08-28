from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from panopticon.probe.client import McpClient
from panopticon.probe.driver import CallDriver, DriverStatus
from panopticon.probe.protocol import ProbeStatus

FIXTURE = Path(__file__).parents[2] / "fixtures" / "mcp" / "official_examples.py"


async def spawn(mode: str) -> tuple[asyncio.subprocess.Process, McpClient]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(FIXTURE),
        mode,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    assert process.stdin is not None and process.stdout is not None
    return process, McpClient(process.stdout, process.stdin, timeout=0.5)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["filesystem", "github", "fetch", "memory", "sqlite"])
async def test_official_example_modes_are_runnable(mode: str) -> None:
    process, client = await spawn(mode)
    try:
        assert (await client.initialize()).status is ProbeStatus.COMPLETE
        listed = await client.list_paginated("tools/list", timeout=0.5)
        assert listed.status is ProbeStatus.COMPLETE
        tools = listed.result["tools"]  # type: ignore[index]
        result = await CallDriver(client, calls=2, stage_timeout=0.5, total_timeout=2).run(tools)
        assert result.status is DriverStatus.COMPLETE
        for call in result.calls:
            assert call.response is not None and call.response.status is ProbeStatus.COMPLETE
            tool = next(item for item in tools if item["name"] == call.tool)
            arguments = (
                call.response.result
            )  # server echoes no args; validate generated via direct schema below
            assert isinstance(arguments, dict)
            # Re-generate the exact argument and validate the schema contract.
            generated = CallDriver(client).generator.generate(
                tool["inputSchema"], call_index=call.call_index
            )
            Draft202012Validator(tool["inputSchema"]).validate(generated.value)
    finally:
        await client.close()
        await asyncio.wait_for(process.wait(), timeout=1)


@pytest.mark.asyncio
async def test_protocol_mismatch_crash_and_no_response_have_distinct_reasons() -> None:
    process, client = await spawn("mismatch")
    try:
        result = await client.initialize(timeout=0.2)
        assert result.status is ProbeStatus.UNSUPPORTED
        assert result.reason_code == "PROTOCOL_VERSION_MISMATCH"
    finally:
        await client.close()
        await asyncio.wait_for(process.wait(), timeout=1)

    process, client = await spawn("crash")
    try:
        result = await client.initialize(timeout=0.5)
        assert result.reason_code == "EARLY_EXIT"
    finally:
        await client.close()
        await asyncio.wait_for(process.wait(), timeout=1)

    process, client = await spawn("no-response")
    try:
        assert (await client.initialize()).status is ProbeStatus.COMPLETE
        listed = await client.list_paginated("tools/list", timeout=0.5)
        result = await CallDriver(client, stage_timeout=0.05, total_timeout=0.5).run(
            listed.result["tools"]
        )  # type: ignore[index]
        assert result.reason_code == "TIMEOUT"
    finally:
        await client.close()
        await asyncio.wait_for(process.wait(), timeout=1)
