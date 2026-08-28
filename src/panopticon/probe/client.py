"""Dual-era MCP lifecycle and capability-gated stdio methods."""

from __future__ import annotations

from .argument_schema import JsonValue
from .pagination import list_paginated
from .protocol import (
    LEGACY_PROTOCOL,
    MAX_FRAME,
    MODERN_PROTOCOL,
    AsyncByteReader,
    AsyncByteWriter,
    ProbeResult,
    ProbeStatus,
    ProtocolEra,
)
from .stdio import StdioTransport


class McpClient(StdioTransport):
    def __init__(
        self,
        reader: AsyncByteReader,
        writer: AsyncByteWriter,
        *,
        timeout: float = 30.0,
        max_frame: int = MAX_FRAME,
        protocol: str = MODERN_PROTOCOL,
    ) -> None:
        super().__init__(
            reader,
            writer,
            timeout=timeout,
            max_frame=max_frame,
            protocol=protocol,
        )
        self.capabilities: dict[str, JsonValue] = {}
        self.server_info: dict[str, JsonValue] = {}

    async def initialize(self, *, timeout: float | None = None) -> ProbeResult:
        modern = await self._initialize_version(self.protocol, timeout, modern=True)
        if modern.status is ProbeStatus.COMPLETE:
            self.era = ProtocolEra.MODERN
            self._record_server(modern.result)
            if "serverDiscovery" in self.capabilities:
                discovered = await self.request("server/discover", timeout=timeout)
                if discovered.status is not ProbeStatus.COMPLETE:
                    return discovered
            return modern
        if self._closed or self._desynchronized:
            return modern
        legacy = await self._initialize_version(LEGACY_PROTOCOL, timeout, modern=False)
        if legacy.status is ProbeStatus.COMPLETE:
            self.era = ProtocolEra.LEGACY
            self._record_server(legacy.result)
            await self.notify("notifications/initialized", {}, modern_metadata=False)
            return ProbeResult(ProbeStatus.COMPLETE, "LEGACY_FALLBACK", legacy.result)
        if (
            modern.reason_code == "PROTOCOL_VERSION_MISMATCH"
            and legacy.reason_code == "PROTOCOL_VERSION_MISMATCH"
        ):
            return ProbeResult(ProbeStatus.UNSUPPORTED, "PROTOCOL_VERSION_MISMATCH")
        return ProbeResult(ProbeStatus.UNSUPPORTED, "PROTOCOL_UNSUPPORTED")

    async def _initialize_version(
        self,
        version: str,
        timeout: float | None,
        *,
        modern: bool,
    ) -> ProbeResult:
        result = await self.request(
            "initialize",
            {
                "protocolVersion": version,
                "capabilities": {},
                "clientInfo": {"name": "panopticon", "version": "0"},
            },
            timeout=timeout,
            modern_metadata=modern,
        )
        # A successful JSON-RPC response is not sufficient: MCP negotiation
        # must echo a protocol revision supported by this request.  Treat an
        # echoed (or selected) different revision as a typed mismatch so the
        # caller can perform the legacy retry rather than entering the wrong
        # era.
        if result.status is ProbeStatus.COMPLETE:
            payload = result.result
            selected = payload.get("protocolVersion") if isinstance(payload, dict) else None
            if selected is not None and selected != version:
                return ProbeResult(ProbeStatus.UNSUPPORTED, "PROTOCOL_VERSION_MISMATCH", payload)
        if result.status is ProbeStatus.COMPLETE and modern:
            self.era = ProtocolEra.MODERN
            await self.notify("notifications/initialized", {})
        return result

    def _record_server(self, value: JsonValue) -> None:
        if not isinstance(value, dict):
            return
        capabilities = value.get("capabilities")
        information = value.get("serverInfo")
        if isinstance(capabilities, dict):
            self.capabilities = capabilities
        if isinstance(information, dict):
            self.server_info = information

    async def list_paginated(self, method: str, *, timeout: float | None = None) -> ProbeResult:
        return await list_paginated(self, self.capabilities, method, timeout=timeout)


AsyncMcpClient = McpClient

__all__ = [
    "AsyncMcpClient",
    "McpClient",
    "ProbeResult",
    "ProbeStatus",
    "ProtocolEra",
]
