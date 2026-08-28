"""Bounded deterministic MCP tool call driver."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .argument_schema import JsonValue, Schema
from .arguments import ArgumentGenerator
from .overrides import parse_overrides as parse_overrides
from .protocol import ProbeResult, ProbeStatus


class DriverStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    INCOMPLETE = "INCOMPLETE"


class CallStatus(StrEnum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    UNPROBEABLE = "UNPROBEABLE"


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    schema: Schema
    destructive: bool = False


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    tool: str
    call_index: int
    status: CallStatus
    reason_code: str
    response: ProbeResult | None = None


@dataclass(frozen=True, slots=True)
class DriverResult:
    status: DriverStatus
    reason_code: str
    calls: tuple[ToolCallResult, ...] = ()


class ProbeClient(Protocol):
    async def list_paginated(self, method: str, *, timeout: float | None = None) -> ProbeResult: ...

    async def request(
        self,
        method: str,
        params: dict[str, JsonValue] | None = None,
        *,
        timeout: float | None = None,
    ) -> ProbeResult: ...


class CallDriver:
    def __init__(
        self,
        client: ProbeClient,
        *,
        calls: int = 1,
        stage_timeout: float = 20.0,
        total_timeout: float = 120.0,
        seed: str = "panopticon-probe",
        real_env: bool = False,
    ) -> None:
        if calls < 0 or stage_timeout <= 0 or total_timeout <= 0:
            raise ValueError("driver bounds must be non-negative and timeouts positive")
        self.client = client
        self.call_count = calls
        self.stage_timeout = stage_timeout
        self.total_timeout = total_timeout
        self.generator = ArgumentGenerator(seed)
        self.real_env = real_env
        self._task: asyncio.Task[DriverResult] | None = None

    async def run(
        self,
        tools: list[dict[str, object]] | tuple[dict[str, object], ...] | None = None,
        *,
        overrides: dict[str, dict[str, JsonValue]] | None = None,
    ) -> DriverResult:
        self._task = asyncio.current_task()
        try:
            async with asyncio.timeout(self.total_timeout):
                definitions_result = await self._definitions(tools)
                if isinstance(definitions_result, DriverResult):
                    return definitions_result
                definitions = definitions_result
                if self.call_count == 0 or not definitions:
                    return DriverResult(DriverStatus.COMPLETE, "ZERO_TOOLS")
                return await self._run_calls(definitions, overrides or {})
        except TimeoutError:
            return DriverResult(DriverStatus.INCOMPLETE, "TOTAL_TIMEOUT")
        except asyncio.CancelledError:
            return DriverResult(DriverStatus.CANCELLED, "CANCELLED")
        finally:
            self._task = None

    async def _definitions(
        self,
        tools: list[dict[str, object]] | tuple[dict[str, object], ...] | None,
    ) -> tuple[ToolDefinition, ...] | DriverResult:
        raw_tools: object = tools
        if raw_tools is None:
            listed = await self.client.list_paginated("tools/list", timeout=self.stage_timeout)
            if listed.status is ProbeStatus.UNSUPPORTED:
                return DriverResult(DriverStatus.COMPLETE, "ZERO_TOOLS")
            if listed.status is not ProbeStatus.COMPLETE:
                return DriverResult(DriverStatus.INCOMPLETE, listed.reason_code)
            raw_tools = listed.result.get("tools", []) if isinstance(listed.result, dict) else None
        if not isinstance(raw_tools, (list, tuple)):
            return DriverResult(DriverStatus.INCOMPLETE, "MALFORMED_TOOL_LIST")
        definitions: list[ToolDefinition] = []
        for raw_tool in raw_tools:
            definition = _tool_definition(raw_tool)
            if definition is None:
                return DriverResult(DriverStatus.INCOMPLETE, "MALFORMED_TOOL_DEFINITION")
            definitions.append(definition)
        return tuple(sorted(definitions, key=lambda tool: tool.name))

    async def _run_calls(
        self,
        tools: tuple[ToolDefinition, ...],
        overrides: dict[str, dict[str, JsonValue]],
    ) -> DriverResult:
        outcomes: list[ToolCallResult] = []
        for call_index in range(1, self.call_count + 1):
            for tool in tools:
                if self.real_env and tool.destructive:
                    outcomes.append(
                        ToolCallResult(
                            tool.name,
                            call_index,
                            CallStatus.SKIPPED,
                            "SKIPPED_DESTRUCTIVE",
                        )
                    )
                    continue
                arguments = overrides.get(tool.name)
                if arguments is None:
                    generated = self.generator.generate(tool.schema, call_index=call_index)
                    if not generated.supported or not isinstance(generated.value, dict):
                        outcomes.append(
                            ToolCallResult(
                                tool.name,
                                call_index,
                                CallStatus.UNPROBEABLE,
                                generated.reason_code,
                            )
                        )
                        continue
                    arguments = generated.value
                response = await self.client.request(
                    "tools/call",
                    {"name": tool.name, "arguments": arguments},
                    timeout=self.stage_timeout,
                )
                call_status = (
                    CallStatus.COMPLETE
                    if response.status is ProbeStatus.COMPLETE
                    else CallStatus.FAILED
                )
                outcomes.append(
                    ToolCallResult(
                        tool.name,
                        call_index,
                        call_status,
                        response.reason_code,
                        response,
                    )
                )
                if response.reason_code in {
                    "TIMEOUT",
                    "EARLY_EXIT",
                    "STREAM_DESYNCHRONIZED",
                    "TRANSPORT_ERROR",
                }:
                    return DriverResult(
                        DriverStatus.INCOMPLETE,
                        response.reason_code,
                        tuple(outcomes),
                    )
        complete = all(outcome.status is CallStatus.COMPLETE for outcome in outcomes)
        return DriverResult(
            DriverStatus.COMPLETE if complete else DriverStatus.PARTIAL,
            "OK" if complete else "PARTIAL_CALL_COVERAGE",
            tuple(outcomes),
        )

    async def cancel(self) -> DriverResult:
        if (
            self._task is not None
            and not self._task.done()
            and self._task is not asyncio.current_task()
        ):
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        return DriverResult(DriverStatus.CANCELLED, "CANCELLED")


def _tool_definition(value: object) -> ToolDefinition | None:
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    raw_schema = value.get("inputSchema", {})
    if not isinstance(name, str) or not name or not isinstance(raw_schema, (bool, dict)):
        return None
    annotations = value.get("annotations", {})
    annotated = isinstance(annotations, dict) and annotations.get("destructiveHint") is True
    inferred = re.search(r"(?:delete|remove|write|execute|shell|send|publish)", name, re.I)
    return ToolDefinition(name, raw_schema, annotated or inferred is not None)


async def run_calls(
    client: ProbeClient,
    tools: list[dict[str, object]],
    *,
    calls: int = 1,
    timeout: float = 20.0,
    seed: str = "panopticon-probe",
    real_env: bool = False,
) -> DriverResult:
    return await CallDriver(
        client,
        calls=calls,
        stage_timeout=timeout,
        seed=seed,
        real_env=real_env,
    ).run(tools)
