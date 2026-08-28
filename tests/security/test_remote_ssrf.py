from __future__ import annotations

from dataclasses import dataclass

from panopticon.probe.remote import RemoteLimits, RemoteObserver, RemoteRequest, RemoteStatus
from panopticon.probe.remote_security import validate_url


@dataclass
class FakeResponse:
    status: int
    headers: dict[str, str]
    body: bytes = b""
    url: str = "https://public.example.test/mcp"


class FakeClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, str, tuple[tuple[str, str], ...], bytes | None]] = []

    def request(
        self, method: str, url: str, headers: tuple[tuple[str, str], ...], body: bytes | None = None
    ) -> FakeResponse:
        self.calls.append((method, url, headers, body))
        return next(self.responses)


class FakeResolver:
    def __init__(self, addresses: dict[str, tuple[str, ...]]) -> None:
        self.addresses = addresses

    def resolve(self, host: str) -> tuple[str, ...]:
        return self.addresses.get(host, (host,))


def test_metadata_redirect_is_blocked_without_auth_forwarding() -> None:
    blocked = (
        "http://127.0.0.1/mcp",
        "https://10.0.0.2/mcp",
        "https://[::1]/mcp",
        "https://169.254.169.254/latest/meta-data",
        "https://metadata.google.internal/computeMetadata/v1",
        "file:///etc/passwd",
        "unix:///tmp/mcp.sock",
        "https://public.example.test/mcp#fragment",
        "https://user:password@public.example.test/mcp",
    )
    resolver = FakeResolver({"rebind.example.test": ("93.184.216.34", "127.0.0.1")})
    for url in (*blocked, "https://rebind.example.test/mcp"):
        decision = validate_url(url, resolver)
        assert not decision.allowed, url

    client = FakeClient(
        [
            FakeResponse(
                302,
                {"Location": "https://metadata.google.internal/latest", "X-Irrelevant": "secret"},
            ),
            FakeResponse(200, {"Content-Type": "application/json"}, b'{"ok":true}'),
        ]
    )
    request = RemoteRequest(
        "https://public.example.test/mcp?session=private-query",
        headers=(
            ("Authorization", "Bearer raw-token"),
            ("Cookie", "sid=raw-cookie"),
            ("MCP-SESSION-ID", "raw-session"),
            ("X-Custom", "safe"),
        ),
        body=b'{"query":"raw-query"}',
    )
    result = RemoteObserver(client, resolver).observe(request)
    assert result.status is RemoteStatus.UNSUPPORTED
    assert result.reason_code.startswith("REDIRECT_")
    assert len(client.calls) == 1
    assert "metadata" not in repr(result).casefold()
    assert "raw-token" not in repr(result)
    assert "private-query" not in repr(result)

    # A cross-origin redirect must never forward credentials or session state.
    cross_client = FakeClient(
        [
            FakeResponse(302, {"location": "https://other.example.test/new"}),
            FakeResponse(200, {"content-type": "application/json"}, b'{"ok":true}'),
        ]
    )
    cross = RemoteObserver(cross_client).observe(
        RemoteRequest(
            "https://public.example.test/mcp",
            headers=(
                ("authorization", "Bearer token"),
                ("cookie", "a=b"),
                ("mcp-session-id", "s"),
                ("X-Case", "v"),
            ),
            body=b"payload",
        )
    )
    assert cross.status is RemoteStatus.COMPLETE
    method, url, headers, body = cross_client.calls[1]
    assert method == "POST" and url == "https://other.example.test/new" and body == b"payload"
    assert {name.casefold() for name, _ in headers} == {"x-case"}

    # 303 changes POST to GET and 307 preserves method/body; redirect limits are bounded.
    changed = FakeClient(
        [
            FakeResponse(303, {"location": "https://public.example.test/get"}),
            FakeResponse(200, {}, b"{}"),
        ]
    )
    RemoteObserver(changed).observe(RemoteRequest("https://public.example.test/mcp", body=b"x"))
    assert changed.calls[1][0] == "GET" and changed.calls[1][3] is None
    preserved = FakeClient(
        [
            FakeResponse(307, {"location": "https://public.example.test/new"}),
            FakeResponse(200, {}, b"{}"),
        ]
    )
    RemoteObserver(preserved).observe(RemoteRequest("https://public.example.test/mcp", body=b"x"))
    assert preserved.calls[1][0] == "POST" and preserved.calls[1][3] == b"x"

    loop = FakeClient([FakeResponse(302, {"location": "https://public.example.test/next"})] * 3)
    limited = RemoteObserver(loop, limits=RemoteLimits(max_redirects=2))
    assert (
        limited.observe(RemoteRequest("https://public.example.test/mcp")).reason_code
        == "REDIRECT_LIMIT"
    )
