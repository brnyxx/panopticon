"""Bounded JSON-RPC framing supporting newline and Content-Length messages."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import JsonValue, TypeAdapter, ValidationError

DEFAULT_MAX_FRAME = 1_048_576
_JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class FrameError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Frame:
    payload: bytes
    message: JsonValue


def encode(
    message: JsonValue,
    *,
    content_length: bool = False,
    max_frame: int = DEFAULT_MAX_FRAME,
) -> bytes:
    payload = _JSON.dump_json(message)
    if len(payload) > max_frame:
        raise FrameError("FRAME_TOO_LARGE")
    return (
        (b"Content-Length: " + str(len(payload)).encode("ascii") + b"\r\n\r\n" + payload)
        if content_length
        else payload + b"\n"
    )


class Decoder:
    def __init__(self, max_frame: int = DEFAULT_MAX_FRAME) -> None:
        if max_frame < 1:
            raise ValueError("max_frame must be positive")
        self.max_frame = max_frame
        self._buf = bytearray()

    def feed(self, data: bytes) -> tuple[Frame, ...]:
        self._buf.extend(data)
        if len(self._buf) > self.max_frame * 2:
            raise FrameError("BUFFER_OVERFLOW")
        out: list[Frame] = []
        while self._buf:
            marker = self._buf.find(b"\r\n\r\n")
            newline = self._buf.find(b"\n")
            if marker >= 0 and self._buf[:marker].lower().lstrip().startswith(b"content-length:"):
                header = bytes(self._buf[:marker])
                length = self._length(header)
                end = marker + 4 + length
                if len(self._buf) < end:
                    break
                payload = bytes(self._buf[marker + 4 : end])
                del self._buf[:end]
            elif newline >= 0:
                payload = bytes(self._buf[:newline]).rstrip(b"\r")
                del self._buf[: newline + 1]
                if not payload:
                    continue
                if len(payload) > self.max_frame:
                    raise FrameError("FRAME_TOO_LARGE")
            else:
                break
            try:
                message = _JSON.validate_json(payload)
            except ValidationError as exc:
                raise FrameError("MALFORMED_JSON") from exc
            out.append(Frame(payload, message))
        return tuple(out)

    def _length(self, header: bytes) -> int:
        values = [
            line.split(b":", 1)[1].strip()
            for line in header.split(b"\r\n")
            if line.lower().startswith(b"content-length:")
        ]
        if len(values) != 1:
            raise FrameError("MALFORMED_HEADER")
        try:
            length = int(values[0])
        except ValueError as exc:
            raise FrameError("MALFORMED_HEADER") from exc
        if length < 0 or length > self.max_frame:
            raise FrameError("FRAME_TOO_LARGE")
        return length


def decode(data: bytes, max_frame: int = DEFAULT_MAX_FRAME) -> tuple[Frame, ...]:
    return Decoder(max_frame).feed(data)


FrameDecoder = Decoder
encode_message = encode
