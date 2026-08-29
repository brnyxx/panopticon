"""Typed MCP JSON-RPC contracts and bounded stdio framing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .argument_schema import JsonValue, UnsupportedSchemaError, json_value

MODERN_PROTOCOL = "2026-07-28"
LEGACY_PROTOCOL = "2024-11-05"
MAX_FRAME = 1_048_576
# Stable reason codes used by the dual-era negotiation state machine.
PROTOCOL_VERSION_MISMATCH = "PROTOCOL_VERSION_MISMATCH"
SERVER_CRASH = "SERVER_CRASH"
NO_RESPONSE = "NO_RESPONSE"


class ProbeStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNSUPPORTED = "UNSUPPORTED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class ProtocolEra(StrEnum):
    MODERN = "modern"
    LEGACY = "legacy"


@dataclass(frozen=True, slots=True)
class ProtocolError:
    code: int | None
    reason_code: str
    data: JsonValue = None


@dataclass(frozen=True, slots=True)
class ProbeResult:
    status: ProbeStatus
    reason_code: str
    result: JsonValue = None
    error: ProtocolError | None = None


class AsyncByteReader(Protocol):
    async def read(self, size: int) -> bytes: ...


class AsyncByteWriter(Protocol):
    def write(self, data: bytes) -> None: ...

    async def drain(self) -> None: ...

    def close(self) -> None: ...


class FrameError(Exception):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class FrameDecoder:
    def __init__(self, max_frame: int = MAX_FRAME) -> None:
        if max_frame < 1:
            raise ValueError("max_frame must be positive")
        self.max_frame = max_frame
        self.buffer = bytearray()

    def feed(self, chunk: bytes) -> tuple[dict[str, object], ...]:
        self.buffer.extend(chunk)
        if len(self.buffer) > self.max_frame * 2:
            raise FrameError("RESPONSE_TOO_LARGE")
        messages: list[dict[str, object]] = []
        while True:
            if self.buffer.lower().startswith(b"content-length:"):
                marker = self.buffer.find(b"\r\n\r\n")
                if marker < 0:
                    return tuple(messages)
                length = _content_length(bytes(self.buffer[:marker]))
                if length > self.max_frame:
                    raise FrameError("RESPONSE_TOO_LARGE")
                frame_end = marker + 4 + length
                if len(self.buffer) < frame_end:
                    return tuple(messages)
                payload = bytes(self.buffer[marker + 4 : frame_end])
                del self.buffer[:frame_end]
            else:
                marker = self.buffer.find(b"\n")
                if marker < 0:
                    return tuple(messages)
                if marker > self.max_frame:
                    raise FrameError("RESPONSE_TOO_LARGE")
                payload = bytes(self.buffer[:marker]).rstrip(b"\r")
                del self.buffer[: marker + 1]
                if not payload:
                    continue
            try:
                decoded: object = json.loads(payload)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise FrameError("MALFORMED_FRAME") from error
            if not isinstance(decoded, dict):
                raise FrameError("BATCH_UNSUPPORTED")
            messages.append(decoded)


def encode_message(message: dict[str, JsonValue], max_frame: int = MAX_FRAME) -> bytes:
    body = json.dumps(message, ensure_ascii=True, separators=(",", ":")).encode()
    if len(body) > max_frame:
        raise FrameError("REQUEST_TOO_LARGE")
    return body + b"\n"


def response_value(value: object) -> JsonValue:
    try:
        return json_value(value)
    except UnsupportedSchemaError as error:
        raise FrameError("MALFORMED_RESPONSE") from error


def _content_length(header: bytes) -> int:
    values: list[bytes] = []
    for line in header.split(b"\r\n"):
        if b":" not in line:
            raise FrameError("MALFORMED_HEADER")
        name, value = line.split(b":", 1)
        if name.strip().lower() == b"content-length":
            values.append(value.strip())
    if len(values) != 1:
        raise FrameError("MALFORMED_HEADER")
    try:
        length = int(values[0])
    except ValueError as error:
        raise FrameError("MALFORMED_HEADER") from error
    if length < 0:
        raise FrameError("MALFORMED_HEADER")
    return length
