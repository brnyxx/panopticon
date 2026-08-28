"""Bounded asynchronous MCP JSON-RPC stdio client."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

MAX_FRAME = 1_048_576


class ProbeStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNSUPPORTED = "UNSUPPORTED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class ProtocolEra(StrEnum):
    MODERN = "modern"
    LEGACY = "legacy"


@dataclass(frozen=True)
class ProbeResult:
    status: ProbeStatus
    reason_code: str
    result: Any = None
    error: Any = None


class McpClient:
    """JSON-RPC client over byte-oriented streams.

    ``reader`` must provide async ``read(n)`` and ``writer`` a ``write(bytes)``
    method plus optional ``drain``/``close`` methods.
    """

    def __init__(
        self,
        reader: Any,
        writer: Any,
        *,
        timeout: float = 30.0,
        max_frame: int = MAX_FRAME,
        protocol: str = "2026-07-28",
    ) -> None:
        self.reader, self.writer = reader, writer
        self.timeout, self.max_frame, self.protocol = timeout, max_frame, protocol
        self._buffer = bytearray()
        self._next_id = 1
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._closed = False
        self.era: ProtocolEra | None = None
        self.capabilities: dict[str, Any] = {}
        self.server_info: dict[str, Any] = {}

    def _ensure_reader(self) -> None:
        if self._reader_task is None:
            self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            while not self._closed:
                chunk = await self.reader.read(65536)
                if not chunk:
                    raise EOFError("stream ended")
                self._buffer.extend(chunk)
                if len(self._buffer) > self.max_frame * 2:
                    raise ValueError("frame exceeds limit")
                while True:
                    marker = self._buffer.find(b"\r\n\r\n")
                    if marker < 0:
                        break
                    header = bytes(self._buffer[:marker])
                    del self._buffer[: marker + 4]
                    length = _content_length(header)
                    if length is None or length > self.max_frame:
                        raise ValueError("invalid or oversized frame")
                    while len(self._buffer) < length:
                        chunk = await self.reader.read(65536)
                        if not chunk:
                            raise EOFError("stream ended")
                        self._buffer.extend(chunk)
                    payload = bytes(self._buffer[:length])
                    del self._buffer[:length]
                    msg = json.loads(payload)
                    if not isinstance(msg, dict):
                        raise ValueError("batch or non-object response")
                    ident = msg.get("id")
                    if isinstance(ident, int) and ident in self._pending:
                        fut = self._pending.pop(ident)
                        if "error" in msg:
                            fut.set_exception(_RpcError(msg["error"]))
                        else:
                            fut.set_result(msg.get("result"))
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(exc)
            self._pending.clear()

    async def request(
        self, method: str, params: dict[str, Any] | None = None, *, timeout: float | None = None
    ) -> ProbeResult:
        if self._closed:
            return ProbeResult(ProbeStatus.ERROR, "CLIENT_CLOSED")
        self._ensure_reader()
        ident = self._next_id
        self._next_id += 1
        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[ident] = fut
        body = json.dumps(
            {"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}},
            separators=(",", ":"),
        ).encode()
        if len(body) > self.max_frame:
            self._pending.pop(ident, None)
            return ProbeResult(ProbeStatus.ERROR, "REQUEST_TOO_LARGE")
        self.writer.write(b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
        if hasattr(self.writer, "drain"):
            await self.writer.drain()
        try:
            value = await asyncio.wait_for(
                fut, timeout=self.timeout if timeout is None else timeout
            )
            return ProbeResult(ProbeStatus.COMPLETE, "OK", value)
        except TimeoutError:
            self._pending.pop(ident, None)
            return ProbeResult(ProbeStatus.INCOMPLETE, "TIMEOUT")
        except asyncio.CancelledError:
            self._pending.pop(ident, None)
            return ProbeResult(ProbeStatus.CANCELLED, "CANCELLED")
        except _RpcError as exc:
            return ProbeResult(ProbeStatus.ERROR, "SERVER_ERROR", error=exc.error)
        except EOFError:
            return ProbeResult(ProbeStatus.INCOMPLETE, "EARLY_EXIT")
        except Exception as exc:
            return ProbeResult(ProbeStatus.ERROR, "MALFORMED_FRAME", error=str(exc))

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> ProbeResult:
        if self._closed:
            return ProbeResult(ProbeStatus.ERROR, "CLIENT_CLOSED")
        body = json.dumps(
            {"jsonrpc": "2.0", "method": method, "params": params or {}}, separators=(",", ":")
        ).encode()
        if len(body) > self.max_frame:
            return ProbeResult(ProbeStatus.ERROR, "REQUEST_TOO_LARGE")
        self.writer.write(b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
        if hasattr(self.writer, "drain"):
            await self.writer.drain()
        return ProbeResult(ProbeStatus.COMPLETE, "OK")

    async def initialize(self, *, timeout: float | None = None) -> ProbeResult:
        modern = await self.request(
            "initialize",
            {
                "protocolVersion": self.protocol,
                "capabilities": {},
                "clientInfo": {"name": "panopticon", "version": "0"},
            },
            timeout=timeout,
        )
        if modern.status is ProbeStatus.COMPLETE:
            self.era = ProtocolEra.MODERN
            data = modern.result or {}
            self.capabilities = data.get("capabilities", {})
            self.server_info = data.get("serverInfo", {})
            await self.notify("notifications/initialized", {})
            return modern
        legacy = await self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "panopticon", "version": "0"},
            },
            timeout=timeout,
        )
        if legacy.status is ProbeStatus.COMPLETE:
            self.era = ProtocolEra.LEGACY
            data = legacy.result or {}
            self.capabilities = data.get("capabilities", {})
            self.server_info = data.get("serverInfo", {})
            await self.notify("notifications/initialized", {})
            return legacy
        return ProbeResult(ProbeStatus.UNSUPPORTED, "PROTOCOL_UNSUPPORTED")

    async def list_paginated(self, method: str, *, timeout: float | None = None) -> ProbeResult:
        if method == "tools/list" and "tools" not in self.capabilities:
            return ProbeResult(ProbeStatus.UNSUPPORTED, "CAPABILITY_UNSUPPORTED")
        if method == "resources/list" and "resources" not in self.capabilities:
            return ProbeResult(ProbeStatus.UNSUPPORTED, "CAPABILITY_UNSUPPORTED")
        if method == "prompts/list" and "prompts" not in self.capabilities:
            return ProbeResult(ProbeStatus.UNSUPPORTED, "CAPABILITY_UNSUPPORTED")
        out: list[Any] = []
        cursor: str | None = None
        seen: set[str] = set()
        while True:
            res = await self.request(
                method, {} if cursor is None else {"cursor": cursor}, timeout=timeout
            )
            if res.status is not ProbeStatus.COMPLETE:
                return res
            data = res.result or {}
            key = method.split("/")[0]
            out.extend(data.get(key, []))
            nxt = data.get("nextCursor")
            if not nxt:
                return ProbeResult(ProbeStatus.COMPLETE, "OK", {key: out})
            if nxt in seen:
                return ProbeResult(ProbeStatus.ERROR, "DUPLICATE_CURSOR")
            seen.add(nxt)
            cursor = nxt

    async def close(self) -> None:
        self._closed = True
        if self._reader_task:
            self._reader_task.cancel()
            await asyncio.gather(self._reader_task, return_exceptions=True)
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()
        if hasattr(self.writer, "close"):
            self.writer.close()


class _RpcError(Exception):
    def __init__(self, error: Any) -> None:
        self.error = error


def _content_length(header: bytes) -> int | None:
    values = [
        line.split(b":", 1)[1].strip()
        for line in header.split(b"\r\n")
        if line.lower().startswith(b"content-length:") and b":" in line
    ]
    if len(values) != 1:
        return None
    try:
        return int(values[0])
    except ValueError:
        return None


AsyncMcpClient = McpClient
