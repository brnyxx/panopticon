"""Typed runtime and cleanup helpers for local watch sessions."""

from __future__ import annotations

import asyncio
from typing import Protocol

from panopticon.probe.client import McpClient
from panopticon.sandbox.base import (
    Container,
    InteractiveSession,
    Runtime,
    SandboxError,
    StreamResult,
)
from panopticon.sandbox.network import NetworkController, NetworkSession

from .watch_inventory import WatchTargetContext
from .watch_local_model import LocalWatchResult, LocalWatchStatus


class LocalRuntime(Runtime, Protocol):
    executable: str


def unsupported(context: WatchTargetContext, reason: str) -> LocalWatchResult:
    return LocalWatchResult(context, LocalWatchStatus.UNSUPPORTED, reason)


async def bounded_stderr(session: InteractiveSession) -> StreamResult:
    try:
        return await asyncio.wait_for(session.read_stderr(), 0.2)
    except TimeoutError:
        return StreamResult(b"")


async def cleanup_local(
    client: McpClient | None,
    session: InteractiveSession | None,
    container: Container | None,
    controller: NetworkController | None,
    network: NetworkSession | None,
) -> tuple[str, ...]:
    diagnostics: list[str] = []
    try:
        if client is not None:
            await client.close()
        if session is not None:
            await session.cleanup()
        elif container is not None:
            await container.stop()
            await container.rm()
    except (OSError, SandboxError):
        diagnostics.append("CONTAINER_CLEANUP_FAILED")
    try:
        if controller is not None and network is not None:
            await controller.stop(network)
    except (OSError, SandboxError):
        diagnostics.append("NETWORK_CLEANUP_FAILED")
    return tuple(diagnostics)


__all__ = ["LocalRuntime", "bounded_stderr", "cleanup_local", "unsupported"]
