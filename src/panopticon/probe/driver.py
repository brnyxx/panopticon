"""Bounded deterministic MCP tool call driver."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .arguments import ArgumentGenerator
from .client import McpClient, ProbeResult, ProbeStatus


class DriverStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class DriverResult:
    status: DriverStatus
    reason_code: str
    calls: tuple[ProbeResult, ...] = ()


class CallDriver:
    def __init__(
        self,
        client: McpClient,
        *,
        calls: int = 1,
        timeout: float = 20.0,
        seed: str = "panopticon-probe",
    ) -> None:
        self.client, self.calls, self.timeout = client, max(0, calls), timeout
        self.generator = ArgumentGenerator(seed)
        self._task: asyncio.Task[DriverResult] | None = None

    async def run(
        self,
        tools: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
        *,
        overrides: dict[str, dict[str, Any]] | None = None,
    ) -> DriverResult:
        self._task = asyncio.current_task()
        if not tools:
            listed = await self.client.list_paginated("tools/list", timeout=self.timeout)
            if listed.status is ProbeStatus.UNSUPPORTED:
                return DriverResult(DriverStatus.COMPLETE, "ZERO_TOOLS")
            if listed.status is not ProbeStatus.COMPLETE:
                return DriverResult(DriverStatus.INCOMPLETE, listed.reason_code)
            tools = (listed.result or {}).get("tools", [])
        if self.calls == 0 or not tools:
            return DriverResult(DriverStatus.COMPLETE, "ZERO_TOOLS")
        results: list[ProbeResult] = []
        try:
            for index in range(1, self.calls + 1):
                for tool in tools:
                    name = str(tool.get("name", ""))
                    schema = tool.get("inputSchema", {})
                    args = (overrides or {}).get(name)
                    if args is None:
                        generated = self.generator.generate(schema, call_index=index)
                        if not generated.supported:
                            results.append(
                                ProbeResult(ProbeStatus.UNSUPPORTED, generated.reason_code)
                            )
                            continue
                        args = generated.value
                    results.append(
                        await self.client.request(
                            "tools/call", {"name": name, "arguments": args}, timeout=self.timeout
                        )
                    )
            status = (
                DriverStatus.COMPLETE
                if all(x.status is ProbeStatus.COMPLETE for x in results)
                else DriverStatus.PARTIAL
            )
            return DriverResult(
                status, "OK" if status is DriverStatus.COMPLETE else "CALL_FAILED", tuple(results)
            )
        except asyncio.CancelledError:
            return DriverResult(DriverStatus.CANCELLED, "CANCELLED", tuple(results))
        finally:
            self._task = None

    async def cancel(self) -> DriverResult:
        if self._task and not self._task.done() and self._task is not asyncio.current_task():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        return DriverResult(DriverStatus.CANCELLED, "CANCELLED")


async def run_calls(
    client: McpClient,
    tools: list[dict[str, Any]],
    *,
    calls: int = 1,
    timeout: float = 20.0,
    seed: str = "panopticon-probe",
) -> DriverResult:
    return await CallDriver(client, calls=calls, timeout=timeout, seed=seed).run(tools)
