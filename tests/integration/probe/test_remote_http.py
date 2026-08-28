from __future__ import annotations

import hashlib
from dataclasses import dataclass

from panopticon.probe.remote import RemoteLimits, RemoteObserver, RemoteRequest, RemoteStatus


@dataclass
class FakeResponse:
    status: int
    headers: dict[str, str]
    body: bytes = b""
    url: str = "https://api.example.test/mcp"


class FakeClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, str, tuple[tuple[str, str], ...], bytes | None]] = []

    def request(
        self, method: str, url: str, headers: tuple[tuple[str, str], ...], body: bytes | None = None
    ) -> FakeResponse:
        self.calls.append((method, url, headers, body))
        return next(self.responses)


def _values(result: object) -> str:
    return repr(result)


def test_sessionful_streamable_http_records_events() -> None:
    secret = "decoy-session-secret"
    response = FakeResponse(
        200,
        {"Content-Type": "Text/Event-Stream", "MCP-SESSION-ID": "session-7"},
        (
            b": reflected "
            + secret.encode()
            + b'\n\ndata: {"jsonrpc":"2.0","result":{"message":"ok"}}\n\n'
        ),
    )
    client = FakeClient(
        [response, FakeResponse(200, {"content-type": "application/json"}, b'{"ok":true}')]
    )
    observer = RemoteObserver(client)
    request = RemoteRequest(
        "http://API.example.test/mcp?token=must-not-persist",
        headers=(("Authorization", "Bearer raw-secret"), ("X-Trace", "trace-value")),
        body=b'{"method":"initialize","params":{"password":"raw-secret"}}',
        decoys=(("session", secret),),
    )

    result = observer.observe(request)
    assert result.status is RemoteStatus.COMPLETE
    assert result.session_fingerprint == hashlib.sha256(b"session-7").hexdigest()[:16]
    assert result.messages and result.messages[0]["jsonrpc"] == "2.0"
    assert any(event.kind == "net" and event.op == "connect" for event in result.events)
    plaintext = next(event for event in result.events if event.kind == "plaintext_http")
    assert plaintext.path == "/mcp" and plaintext.host == "api.example.test"
    assert set(plaintext.names) == {"authorization", "x-trace"}
    leak = next(event for event in result.events if event.kind == "leak")
    assert leak.decoy_key == "session" and leak.path == "response"
    assert secret not in _values(result) and "raw-secret" not in _values(result)

    resumed = observer.resume(request, "cursor-4")
    method, url, headers, body = client.calls[-1]
    assert resumed.status is RemoteStatus.COMPLETE
    assert method == "GET" and url == "http://api.example.test/mcp"
    assert body == b""
    assert ("Mcp-Session-Id", "session-7") in headers
    assert ("Last-Event-ID", "cursor-4") in headers
    assert "token" not in url and "raw-secret" not in _values(resumed)

    # Legacy fallback is a GET and does not replay the POST body.
    fallback_client = FakeClient(
        [
            FakeResponse(405, {}, b""),
            FakeResponse(200, {"Content-Type": "application/json"}, b'{"ok":true}'),
        ]
    )
    fallback = RemoteObserver(fallback_client).legacy(request)
    assert fallback.status is RemoteStatus.COMPLETE
    assert [call[0] for call in fallback_client.calls] == ["POST", "GET"]
    assert fallback_client.calls[-1][3] == b""

    limited = RemoteObserver(client, limits=RemoteLimits(max_request_bytes=4))
    assert (
        limited.observe(RemoteRequest("https://api.example.test/mcp", body=b"12345")).reason_code
        == "LIMIT_EXCEEDED"
    )
    url_limited = RemoteObserver(client, limits=RemoteLimits(max_url_length=8))
    assert (
        url_limited.observe(RemoteRequest("https://api.example.test/mcp")).reason_code
        == "LIMIT_EXCEEDED"
    )
    huge = RemoteObserver(
        FakeClient([FakeResponse(200, {}, b"12345")]), limits=RemoteLimits(max_response_bytes=4)
    )
    assert (
        huge.observe(RemoteRequest("https://api.example.test/mcp")).reason_code == "RESPONSE_LIMIT"
    )
