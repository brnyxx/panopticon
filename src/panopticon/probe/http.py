"""Bounded dual-era MCP Streamable HTTP transport."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from .argument_schema import JsonValue, UnsupportedSchemaError, json_value
from .http_redirect import post_with_redirects, response_payload, sse_endpoint
from .pagination import list_paginated
from .protocol import (
    LEGACY_PROTOCOL,
    MAX_FRAME,
    MODERN_PROTOCOL,
    ProbeResult,
    ProbeStatus,
    ProtocolEra,
    ProtocolError,
)
from .remote_security import Resolver, validate_url


@dataclass(frozen=True, slots=True)
class TransportEraCache:
    entries: tuple[tuple[str, ProtocolEra], ...] = ()

    def get(self, endpoint: str) -> ProtocolEra | None:
        return dict(self.entries).get(endpoint)

    def with_entry(self, endpoint: str, era: ProtocolEra) -> TransportEraCache:
        values = dict(self.entries)
        values[endpoint] = era
        return TransportEraCache(tuple(sorted(values.items())))


class StreamableHttpClient:
    def __init__(
        self,
        endpoint: str,
        client: httpx.AsyncClient,
        *,
        timeout: float = 30.0,
        max_response: int = MAX_FRAME,
        era_cache: TransportEraCache | None = None,
        headers: tuple[tuple[str, str], ...] = (),
        resolver: Resolver | None = None,
        max_redirects: int = 5,
    ) -> None:
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("MCP HTTP endpoint must be HTTP(S)")
        if timeout <= 0 or max_response < 1 or max_redirects < 0:
            raise ValueError("HTTP transport bounds must be positive")
        self.endpoint = endpoint
        self.client = client
        self.timeout = timeout
        self.max_response = max_response
        self.era_cache = era_cache or TransportEraCache()
        self._headers = dict(headers)
        self._resolver = resolver
        self._max_redirects = max_redirects
        self.era: ProtocolEra | None = self.era_cache.get(endpoint)
        self.session_id: str | None = None
        self.capabilities: dict[str, JsonValue] = {}
        self.server_info: dict[str, JsonValue] = {}
        self._next_id = 1
        self._closed = False
        self.close_reason: str | None = None

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
        identifier = self._next_id
        self._next_id += 1
        request_params = dict(params or {})
        add_metadata = (
            self.era is ProtocolEra.MODERN if modern_metadata is None else modern_metadata
        )
        if add_metadata:
            request_params["_meta"] = {"client": "panopticon", "protocolVersion": MODERN_PROTOCOL}
        message: dict[str, JsonValue] = {
            "jsonrpc": "2.0",
            "id": identifier,
            "method": method,
            "params": request_params,
        }
        headers = {
            **self._headers,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self.session_id is not None:
            headers["Mcp-Session-Id"] = self.session_id
        result = await post_with_redirects(
            self.client,
            self.endpoint,
            message,
            headers,
            timeout=self.timeout if timeout is None else timeout,
            resolver=self._resolver,
            max_redirects=self._max_redirects,
        )
        if isinstance(result, ProbeResult):
            return result
        response, endpoint, _ = result
        if len(response.content) > self.max_response:
            return ProbeResult(ProbeStatus.ERROR, "RESPONSE_TOO_LARGE")
        if response.status_code >= 500:
            return ProbeResult(ProbeStatus.INCOMPLETE, "SERVER_CRASH")
        if response.status_code >= 400:
            return ProbeResult(ProbeStatus.ERROR, "HTTP_ERROR")
        session = response.headers.get("Mcp-Session-Id")
        if session:
            self.session_id = session
        self.endpoint = endpoint
        try:
            payload = response_payload(response)
        except (ValueError, UnicodeDecodeError, UnsupportedSchemaError):
            return ProbeResult(ProbeStatus.ERROR, "MALFORMED_RESPONSE")
        if not isinstance(payload, dict) or payload.get("id") != identifier:
            return ProbeResult(ProbeStatus.ERROR, "MALFORMED_RESPONSE")
        if "error" in payload:
            raw_error = payload["error"]
            if not isinstance(raw_error, dict):
                return ProbeResult(ProbeStatus.ERROR, "MALFORMED_RESPONSE")
            code = raw_error.get("code")
            data = json_value(raw_error.get("data")) if "data" in raw_error else None
            return ProbeResult(
                ProbeStatus.ERROR,
                "SERVER_ERROR",
                error=ProtocolError(code if isinstance(code, int) else None, "SERVER_ERROR", data),
            )
        return ProbeResult(ProbeStatus.COMPLETE, "OK", json_value(payload.get("result")))

    async def notify(
        self,
        method: str,
        params: dict[str, JsonValue] | None = None,
    ) -> ProbeResult:
        if self._closed:
            return ProbeResult(ProbeStatus.ERROR, "CLIENT_CLOSED")
        request_params = dict(params or {})
        if self.era is ProtocolEra.MODERN:
            request_params["_meta"] = {"client": "panopticon"}
        message: dict[str, JsonValue] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": request_params,
        }
        headers = {**self._headers, "Content-Type": "application/json"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        try:
            response = await self.client.post(
                self.endpoint,
                json=message,
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.TimeoutException:
            return ProbeResult(ProbeStatus.INCOMPLETE, "TIMEOUT")
        except httpx.TransportError:
            return ProbeResult(ProbeStatus.INCOMPLETE, "TRANSPORT_ERROR")
        status = ProbeStatus.COMPLETE if response.status_code < 400 else ProbeStatus.ERROR
        return ProbeResult(status, "OK" if status is ProbeStatus.COMPLETE else "HTTP_ERROR")

    async def initialize(self) -> ProbeResult:
        preferred = self.era or ProtocolEra.MODERN
        fallback = ProtocolEra.LEGACY if preferred is ProtocolEra.MODERN else ProtocolEra.MODERN
        order = (preferred, fallback)
        for era in order:
            version = MODERN_PROTOCOL if era is ProtocolEra.MODERN else LEGACY_PROTOCOL
            result = await self.request(
                "initialize",
                {
                    "protocolVersion": version,
                    "capabilities": {},
                    "clientInfo": {"name": "panopticon", "version": "0"},
                },
                modern_metadata=era is ProtocolEra.MODERN,
            )
            if result.reason_code == "HTTP_ERROR" and era is ProtocolEra.MODERN:
                # Deprecated SSE servers expose a GET stream first and accept
                # JSON-RPC messages at the endpoint announced by its `endpoint`
                # event. Keep this fallback bounded and use the same instrumented
                # client so the handshake remains observable.
                try:
                    stream = await self.client.get(
                        self.endpoint,
                        headers={**self._headers, "Accept": "text/event-stream"},
                        timeout=self.timeout,
                    )
                    if stream.status_code < 400:
                        endpoint = sse_endpoint(stream.text)
                        if endpoint is not None:
                            decision = validate_url(
                                urljoin(self.endpoint, endpoint), self._resolver
                            )
                            if decision.allowed:
                                self.endpoint = decision.transport_url
                                result = await self.request(
                                    "initialize",
                                    {
                                        "protocolVersion": version,
                                        "capabilities": {},
                                        "clientInfo": {"name": "panopticon", "version": "0"},
                                    },
                                    modern_metadata=False,
                                )
                except (httpx.TimeoutException, httpx.TransportError):
                    pass
            if result.status is not ProbeStatus.COMPLETE:
                continue
            self.era = era
            self.era_cache = self.era_cache.with_entry(self.endpoint, era)
            self._record_server(result.result)
            await self.notify("notifications/initialized", {})
            reason = "OK" if era is ProtocolEra.MODERN else "LEGACY_FALLBACK"
            return ProbeResult(ProbeStatus.COMPLETE, reason, result.result)
        return ProbeResult(ProbeStatus.UNSUPPORTED, "PROTOCOL_UNSUPPORTED")

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

    async def close(self) -> None:
        self._closed = True
        if self.session_id is not None:
            try:
                await self.client.delete(
                    self.endpoint,
                    headers={**self._headers, "Mcp-Session-Id": self.session_id},
                    timeout=self.timeout,
                )
            except (httpx.TimeoutException, httpx.TransportError):
                self.close_reason = "SESSION_DELETE_FAILED"
