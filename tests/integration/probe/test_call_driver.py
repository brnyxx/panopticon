from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator

from panopticon.probe.argument_schema import JsonValue
from panopticon.probe.driver import CallDriver, DriverStatus
from panopticon.probe.protocol import ProbeResult, ProbeStatus


class ValidatingClient:
    def __init__(self, tools: list[dict[str, object]]) -> None:
        self.tools = tools
        self.arguments: list[tuple[str, dict[str, JsonValue]]] = []

    async def list_paginated(
        self,
        _method: str,
        *,
        timeout: float | None = None,
    ) -> ProbeResult:
        del timeout
        return ProbeResult(ProbeStatus.COMPLETE, "OK", {"tools": self.tools})

    async def request(
        self,
        _method: str,
        params: dict[str, JsonValue] | None = None,
        *,
        timeout: float | None = None,
    ) -> ProbeResult:
        del timeout
        assert params is not None
        name = params["name"]
        arguments = params["arguments"]
        assert isinstance(name, str)
        assert isinstance(arguments, dict)
        schema = next(tool["inputSchema"] for tool in self.tools if tool["name"] == name)
        Draft202012Validator(schema).validate(arguments)
        self.arguments.append((name, arguments))
        return ProbeResult(ProbeStatus.COMPLETE, "OK", {})


@pytest.mark.asyncio
async def test_generated_arguments_cover_pinned_clean_tools() -> None:
    tools: list[dict[str, object]] = [
        {
            "name": "bounded_search",
            "inputSchema": {
                "type": "object",
                "required": ["query", "limit", "tags"],
                "properties": {
                    "query": {"type": "string", "minLength": 3},
                    "limit": {"type": "integer", "minimum": 2, "maximum": 6},
                    "tags": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"enum": ["fixture"]},
                    },
                },
            },
        },
        {
            "name": "describe",
            "inputSchema": {
                "type": "object",
                "required": ["uri"],
                "properties": {"uri": {"type": "string", "format": "uri"}},
            },
        },
    ]
    first = ValidatingClient(tools)
    second = ValidatingClient(tools)

    first_result = await CallDriver(first, calls=2, seed="installation-a").run()
    second_result = await CallDriver(second, calls=2, seed="installation-a").run()

    assert first_result.status is DriverStatus.COMPLETE
    assert second_result.status is DriverStatus.COMPLETE
    assert first.arguments == second.arguments
    assert [name for name, _ in first.arguments] == [
        "bounded_search",
        "describe",
        "bounded_search",
        "describe",
    ]
