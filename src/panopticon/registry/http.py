"""Concrete typed registry HTTP and clock boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import httpx


@dataclass(frozen=True, slots=True)
class HttpOutcome:
    status_code: int | None
    headers: tuple[tuple[str, str], ...] = ()
    body: object = None
    reason_code: str = "OK"


class RegistryHttp(Protocol):
    async def get(
        self,
        url: str,
        *,
        headers: tuple[tuple[str, str], ...],
        timeout: float,
    ) -> HttpOutcome: ...


class HttpxRegistryHttp:
    """Map bounded HTTP responses and expected transport failures to values."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def get(
        self, url: str, *, headers: tuple[tuple[str, str], ...], timeout: float
    ) -> HttpOutcome:
        client = self._client
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=timeout)
        try:
            response = await client.get(url, headers=dict(headers), timeout=timeout)
            if response.status_code == 304:
                body: object = None
            else:
                try:
                    body = response.json()
                except (ValueError, UnicodeDecodeError):
                    return HttpOutcome(response.status_code, reason_code="MALFORMED_JSON")
            return HttpOutcome(
                response.status_code,
                tuple((str(key), str(value)) for key, value in response.headers.items()),
                body,
            )
        except httpx.TimeoutException:
            return HttpOutcome(None, reason_code="TIMEOUT")
        except httpx.TransportError:
            return HttpOutcome(None, reason_code="TRANSPORT_ERROR")
        finally:
            if owns_client:
                await client.aclose()


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class Clock(Protocol):
    def now(self) -> datetime: ...


__all__ = ["Clock", "HttpOutcome", "HttpxRegistryHttp", "RegistryHttp", "SystemClock"]
