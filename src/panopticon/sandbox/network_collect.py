"""Bounded runtime collection for proxy and DNS service logs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath

from .base import ExecResult
from .netlog import (
    NetworkLogReason,
    NetworkLogResult,
    NetworkLogStatus,
    parse_dns_log,
    parse_proxy_log,
)

_PROXY_LOG = PurePosixPath("/").joinpath("tmp", "tinyproxy.log")


def _parsed(
    text: str,
    parser: Callable[[str], NetworkLogResult],
) -> NetworkLogResult:
    if text:
        return parser(text)
    return NetworkLogResult(
        (),
        NetworkLogStatus.FAILED,
        NetworkLogReason.MALFORMED_LINE,
        ("LOG_UNAVAILABLE",),
    )


async def collect_service_logs(
    command: Callable[[list[str]], Awaitable[ExecResult]],
    dns_id: str,
    proxy_id: str,
) -> tuple[NetworkLogResult, NetworkLogResult]:
    async def logs(container_id: str) -> str:
        result = await command(["logs", "--timestamps", "--tail", "10000", container_id])
        if result.returncode:
            return ""
        return result.stdout.data.decode(errors="replace") + result.stderr.data.decode(
            errors="replace"
        )

    async def proxy_log() -> str:
        result = await command(["exec", proxy_id, "cat", str(_PROXY_LOG)])
        if result.returncode == 0:
            return result.stdout.data.decode(errors="replace")
        return await logs(proxy_id)

    dns_text, proxy_text = await asyncio.gather(logs(dns_id), proxy_log())
    return _parsed(dns_text, parse_dns_log), _parsed(proxy_text, parse_proxy_log)


__all__ = ["collect_service_logs"]
