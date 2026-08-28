import pytest

from panopticon.wrap.framing import Decoder, FrameError, decode, encode


def test_newline_and_content_length_round_trip() -> None:
    message = {"jsonrpc": "2.0", "id": 7, "result": {"text": "ok"}}
    newline = encode(message)
    framed = encode(message, content_length=True)
    assert decode(newline)[0].message == message
    assert decode(framed)[0].payload == newline[:-1]
    assert decode(newline + framed)[1].message == message


def test_non_utf8_payload_is_rejected_without_text_coercion() -> None:
    decoder = Decoder()
    with pytest.raises(FrameError, match="MALFORMED_JSON"):
        decoder.feed(b'{"x":"\xff"}\n')


def test_batch_and_partial_frames_preserve_order() -> None:
    decoder = Decoder()
    first = encode({"id": 1})
    second = encode({"id": 2})
    assert decoder.feed(first[:2]) == ()
    frames = decoder.feed(first[2:] + second)
    assert [frame.message["id"] for frame in frames] == [1, 2]


def test_content_length_waits_for_complete_body() -> None:
    payload = b'{"id":3}'
    wire = b"Content-Length: 8\r\n\r\n" + payload
    decoder = Decoder()
    assert decoder.feed(wire[:-1]) == ()
    assert decoder.feed(wire[-1:])[0].message["id"] == 3


def test_frame_limits_and_malformed_headers_are_bounded() -> None:
    with pytest.raises(FrameError, match="FRAME_TOO_LARGE"):
        encode({"data": "x" * 20}, max_frame=4)
    with pytest.raises(FrameError, match="MALFORMED_HEADER"):
        decode(b"Content-Length: nope\r\n\r\n{}", max_frame=100)
    with pytest.raises(FrameError, match="BUFFER_OVERFLOW"):
        Decoder(max_frame=2).feed(b"xxxxxx")
