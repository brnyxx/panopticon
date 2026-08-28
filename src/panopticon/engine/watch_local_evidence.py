"""Sanitized local-watch metadata and span construction helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol, cast

from panopticon.analyzers.behavior.spans import SpanKind
from panopticon.models.ids import derive_span_id
from panopticon.models.inventory import PackageEcosystem
from panopticon.probe.argument_schema import JsonValue
from panopticon.probe.client import McpClient
from panopticon.probe.driver import CallObserver, parse_overrides
from panopticon.probe.protocol import (
    LEGACY_PROTOCOL,
    MODERN_PROTOCOL,
    ProbeResult,
    ProtocolEra,
)
from panopticon.sandbox.image_catalog import ImageCatalog, ImageStatus

from .watch_inventory import WatchTargetContext
from .watch_local_model import LocalProtocol, LocalSpan, LocalTool
from .watch_model import WatchOptions


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SpanRecorder(CallObserver):
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._pending: dict[tuple[str, int], tuple[datetime, str]] = {}
        self.spans: list[LocalSpan] = []

    async def before_call(
        self, tool: str, call_index: int, arguments: dict[str, JsonValue]
    ) -> None:
        encoded = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()[:16]
        self._pending[(tool, call_index)] = (self._clock.now(), fingerprint)

    async def after_call(self, tool: str, call_index: int, result: ProbeResult) -> None:
        started_at, fingerprint = self._pending.pop((tool, call_index))
        self.spans.append(
            LocalSpan(
                derive_span_id(tool, call_index),
                tool,
                call_index,
                started_at,
                self._clock.now(),
                fingerprint,
                result.reason_code,
                SpanKind.CALL,
            )
        )


def reserved_span(
    name: str,
    kind: SpanKind,
    started_at: datetime,
    ended_at: datetime,
) -> LocalSpan:
    return LocalSpan(
        derive_span_id(name, 0),
        name,
        0,
        started_at,
        ended_at,
        hashlib.sha256(b"{}").hexdigest()[:16],
        "OK",
        kind,
    )


def argument_overrides(values: tuple[str, ...]) -> dict[str, dict[str, JsonValue]]:
    return {
        tool: arguments for value in values for tool, arguments in parse_overrides(value).items()
    }


def image_reference(
    context: WatchTargetContext,
    catalog: ImageCatalog,
    self_source: Path | None,
) -> str | None:
    target = context.target
    package = target.package
    if package is not None:
        ecosystem = "node" if package.ecosystem is PackageEcosystem.NPM else "python"
    else:
        command = PurePosixPath(target.command or "").name.casefold()
        if command in {"node", "npx"}:
            ecosystem = "node"
        elif command in {"python", "python3", "uv", "uvx"}:
            ecosystem = "python"
        elif self_source is not None and str(target.command).startswith("/self/"):
            ecosystem = "generic"
        else:
            return None
    selected = catalog.select(ecosystem)
    return selected.reference if selected.status is ImageStatus.SUPPORTED else None


def target_environment(
    context: WatchTargetContext,
    decoys: Mapping[str, str],
    options: WatchOptions,
    real_values: Mapping[str, str] | None,
) -> dict[str, str]:
    environment = {key: decoys[key] for key in context.target.env_keys if key in decoys}
    if options.real_env and real_values is not None:
        environment.update(
            (key, real_values[key]) for key in context.target.env_keys if key in real_values
        )
    return environment


def local_protocol(client: McpClient) -> LocalProtocol:
    era = client.era or ProtocolEra.MODERN
    selected = MODERN_PROTOCOL if era is ProtocolEra.MODERN else LEGACY_PROTOCOL
    name = client.server_info.get("name")
    version = client.server_info.get("version")
    return LocalProtocol(
        era,
        MODERN_PROTOCOL,
        selected,
        era is ProtocolEra.LEGACY,
        name if isinstance(name, str) and name else "unknown",
        version if isinstance(version, str) and version else "unknown",
        tuple(sorted(client.capabilities)),
    )


def normalize_tools(
    values: object,
) -> tuple[tuple[dict[str, JsonValue], ...], tuple[LocalTool, ...]]:
    if not isinstance(values, list):
        return (), ()
    raw_tools: list[dict[str, JsonValue]] = []
    tools: list[LocalTool] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        name = value.get("name")
        schema = value.get("inputSchema", {})
        annotations = value.get("annotations", {})
        if not isinstance(name, str) or not name or not isinstance(schema, (bool, dict)):
            continue
        annotation_map = annotations if isinstance(annotations, dict) else {}
        encoded = json.dumps(schema, sort_keys=True, separators=(",", ":"))
        raw_tools.append(cast(dict[str, JsonValue], value))
        tools.append(
            LocalTool(
                name,
                hashlib.sha256(encoded.encode()).hexdigest()[:16],
                annotation_map.get("readOnlyHint") is True,
                annotation_map.get("destructiveHint") is True,
                annotation_map.get("openWorldHint") is True,
            )
        )
    ordered = sorted(zip(raw_tools, tools, strict=True), key=lambda pair: pair[1].name)
    return tuple(pair[0] for pair in ordered), tuple(pair[1] for pair in ordered)


__all__ = [
    "Clock",
    "SpanRecorder",
    "SystemClock",
    "argument_overrides",
    "image_reference",
    "local_protocol",
    "normalize_tools",
    "reserved_span",
    "target_environment",
]
