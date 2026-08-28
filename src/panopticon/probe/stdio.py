"""Strict bounded JSON-RPC request transport over MCP stdio."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .argument_schema import JsonValue
from .protocol import (
    MAX_FRAME,
    MODERN_PROTOCOL,
    AsyncByteReader,
    AsyncByteWriter,
    FrameDecoder,
    FrameError,
    ProbeResult,
    ProbeStatus,
    ProtocolEra,
    ProtocolError,
    encode_message,
    response_value,
)


@dataclass(slots=True)
class _RpcError(Exception):
    error: ProtocolError


@dataclass(slots=True)
class _ReadError(Exception):
    reason_code: str


class StdioTransport:
    def __init__(
        self,
        reader: AsyncByteReader,
        writer: AsyncByteWriter,
        *,
        timeout: float = 30.0,
        max_frame: int = MAX_FRAME,
        protocol: str = MODERN_PROTOCOL,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.reader = reader
        self.writer = writer
        self.timeout = timeout
        self.max_frame = max_frame
        self.protocol = protocol
        self._decoder = FrameDecoder(max_frame)
        self._next_id = 1
        self._pending: dict[int, asyncio.Future[JsonValue]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._closed = False
        self._desynchronized = False
        self.era: ProtocolEra | None = None

    def _ensure_reader(self) -> None:
        if self._reader_task is None:
            self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        reason = "EARLY_EXIT"
        try:
            while not self._closed:
                chunk = await self.reader.read(65536)
                if not chunk:
                    break
                for message in self._decoder.feed(chunk):
                    self._resolve(message)
            if self._decoder.buffer:
                reason = "TRUNCATED_FRAME"
        except asyncio.CancelledError:
            return
        except FrameError as error:
            reason = error.reason_code
        self._desynchronized = True
        self._fail_pending(reason)

    def _resolve(self, message: dict[str, object]) -> None:
        identifier = message.get("id")
        if not isinstance(identifier, int):
            raise FrameError("MALFORMED_RESPONSE")
        future = self._pending.pop(identifier, None)
        if future is None or future.done():
            return
        if "error" in message:
            raw_error = message["error"]
            if not isinstance(raw_error, dict):
                raise FrameError("MALFORMED_RESPONSE")
            code = raw_error.get("code")
            data = response_value(raw_error.get("data")) if "data" in raw_error else None
            future.set_exception(
                _RpcError(
                    ProtocolError(
                        code if isinstance(code, int) else None,
                        "SERVER_ERROR",
                        data,
                    )
                )
            )
        else:
            future.set_result(response_value(message.get("result")))

    def _fail_pending(self, reason_code: str) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(_ReadError(reason_code))
        self._pending.clear()

    async def request(
        self,
        method: str,
        params: dict[str, JsonValue] | None = None,
        *,
        timeout: float | None = None,
        modern_metadata: bool | None = None,
    ) -> ProbeResult:
        if self._closed:
            return ProbeResult(ProbeStatus.ERROR, "CLIENT_CLOSED")
        if self._desynchronized:
            return ProbeResult(ProbeStatus.INCOMPLETE, "STREAM_DESYNCHRONIZED")
        self._ensure_reader()
        identifier = self._next_id
        self._next_id += 1
        future: asyncio.Future[JsonValue] = asyncio.get_running_loop().create_future()
        self._pending[identifier] = future
        request_params = self._params(params, modern_metadata)
        message: dict[str, JsonValue] = {
            "jsonrpc": "2.0",
            "id": identifier,
            "method": method,
            "params": request_params,
        }
        try:
            self.writer.write(encode_message(message, self.max_frame))
            await self.writer.drain()
        except FrameError as error:
            self._pending.pop(identifier, None)
            return ProbeResult(ProbeStatus.ERROR, error.reason_code)
        try:
            value = await asyncio.wait_for(future, self.timeout if timeout is None else timeout)
        except TimeoutError:
            self._pending.pop(identifier, None)
            await self._abort()
            return ProbeResult(ProbeStatus.INCOMPLETE, "TIMEOUT")
        except asyncio.CancelledError:
            self._pending.pop(identifier, None)
            await self._notify_cancelled(identifier)
            return ProbeResult(ProbeStatus.CANCELLED, "CANCELLED")
        except _RpcError as error:
            return ProbeResult(ProbeStatus.ERROR, "SERVER_ERROR", error=error.error)
        except _ReadError as error:
            incomplete = {"EARLY_EXIT", "TRUNCATED_FRAME"}
            status = (
                ProbeStatus.INCOMPLETE if error.reason_code in incomplete else ProbeStatus.ERROR
            )
            return ProbeResult(status, error.reason_code)
        return ProbeResult(ProbeStatus.COMPLETE, "OK", value)

    async def notify(
        self,
        method: str,
        params: dict[str, JsonValue] | None = None,
        *,
        modern_metadata: bool | None = None,
    ) -> ProbeResult:
        if self._closed or self._desynchronized:
            reason = "CLIENT_CLOSED" if self._closed else "STREAM_DESYNCHRONIZED"
            return ProbeResult(ProbeStatus.ERROR, reason)
        message: dict[str, JsonValue] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": self._params(params, modern_metadata),
        }
        try:
            self.writer.write(encode_message(message, self.max_frame))
            await self.writer.drain()
        except FrameError as error:
            return ProbeResult(ProbeStatus.ERROR, error.reason_code)
        return ProbeResult(ProbeStatus.COMPLETE, "OK")

    def _params(
        self,
        params: dict[str, JsonValue] | None,
        modern_metadata: bool | None,
    ) -> dict[str, JsonValue]:
        output = dict(params or {})
        add_metadata = (
            self.era is ProtocolEra.MODERN if modern_metadata is None else modern_metadata
        )
        if add_metadata:
            output["_meta"] = {"client": "panopticon", "protocolVersion": MODERN_PROTOCOL}
        return output

    async def _notify_cancelled(self, identifier: int) -> None:
        if not self._closed and not self._desynchronized:
            await self.notify("notifications/cancelled", {"requestId": identifier})

    async def _abort(self) -> None:
        self._desynchronized = True
        if self._reader_task is not None:
            self._reader_task.cancel()
            await asyncio.gather(self._reader_task, return_exceptions=True)
        self.writer.close()

    async def close(self) -> None:
        self._closed = True
        if self._reader_task is not None:
            self._reader_task.cancel()
            await asyncio.gather(self._reader_task, return_exceptions=True)
        self._fail_pending("CLIENT_CLOSED")
        self.writer.close()
