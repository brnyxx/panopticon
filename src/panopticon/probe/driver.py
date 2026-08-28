"""Bounded deterministic MCP tool call driver."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .argument_schema import JsonValue
from .arguments import ArgumentGenerator
from .driver_tools import ToolDefinition, tool_definition
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


class CallObserver(Protocol):
    async def before_call(
        self, tool: str, call_index: int, arguments: dict[str, JsonValue]
    ) -> None: ...

    async def after_call(self, tool: str, call_index: int, result: ProbeResult) -> None: ...


class CallObserverError(RuntimeError):
    """Expected observer boundary failure."""


class CallDriver:
    def __init__(
        self,
        client: ProbeClient,
        *,
        calls: int = 1,
        stage_timeout: float = 20.0,
        total_timeout: float = 120.0,
        seed: str = "panopticon-probe",
        allow_destructive: bool = False,
        observer: CallObserver | None = None,
    ) -> None:
        if calls < 0 or stage_timeout <= 0 or total_timeout <= 0:
            raise ValueError("driver bounds must be non-negative and timeouts positive")
        self.client = client
        self.call_count = calls
        self.stage_timeout = stage_timeout
        self.total_timeout = total_timeout
        self.generator = ArgumentGenerator(seed)
        self.allow_destructive = allow_destructive
        self.observer = observer
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
            definition = tool_definition(raw_tool)
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
                if not self.allow_destructive and tool.destructive:
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
                if self.observer is not None:
                    try:
                        await self.observer.before_call(tool.name, call_index, arguments)
                    except CallObserverError:
                        outcomes.append(
                            ToolCallResult(
                                tool.name,
                                call_index,
                                CallStatus.FAILED,
                                "OBSERVER_BEFORE_FAILED",
                            )
                        )
                        return DriverResult(
                            DriverStatus.INCOMPLETE,
                            "OBSERVER_BEFORE_FAILED",
                            tuple(outcomes),
                        )
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
                if self.observer is not None:
                    try:
                        await self.observer.after_call(tool.name, call_index, response)
                    except CallObserverError:
                        return DriverResult(
                            DriverStatus.INCOMPLETE,
                            "OBSERVER_AFTER_FAILED",
                            tuple(outcomes),
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


async def run_calls(
    client: ProbeClient,
    tools: list[dict[str, object]],
    *,
    calls: int = 1,
    timeout: float = 20.0,
    seed: str = "panopticon-probe",
    allow_destructive: bool = False,
    observer: CallObserver | None = None,
) -> DriverResult:
    return await CallDriver(
        client,
        calls=calls,
        stage_timeout=timeout,
        seed=seed,
        allow_destructive=allow_destructive,
        observer=observer,
    ).run(tools)
