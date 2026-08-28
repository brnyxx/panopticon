"""Continuous wrap command composition over the transparent relay core."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path

from panopticon.store.contracts import PersistSuccess
from panopticon.store.repository import ArtifactRepository
from panopticon.wrap.model import RelayResult, WrapRecordCandidate
from panopticon.wrap.persist import persist_record
from panopticon.wrap.process import run_stdio_command
from panopticon.wrap.record import IsolatedRecorder


@dataclass(frozen=True, slots=True)
class WrapRequest:
    command: tuple[str, ...]
    server_id: str | None = None
    installation_id: str | None = None
    root: Path | None = None


@dataclass(frozen=True, slots=True)
class WrapCommandResult:
    relay: RelayResult | None
    exit_code: int
    reason_code: str


class _RecordSink:
    def __init__(self, repository: ArtifactRepository) -> None:
        self._repository = repository

    def record(self, record: WrapRecordCandidate) -> None:
        result = persist_record(self._repository, record)
        if not isinstance(result, PersistSuccess):
            raise OSError("WRAP_RECORD_PERSIST_FAILED")


def _identities(request: WrapRequest) -> tuple[str, str]:
    command_name = Path(request.command[0]).name
    server_id = request.server_id or f"local:{command_name}"
    digest = hashlib.sha256("\0".join(request.command).encode()).hexdigest()[:16]
    installation_id = request.installation_id or f"inst_{digest}"
    return server_id, installation_id


async def _run(request: WrapRequest) -> WrapCommandResult:
    if not request.command or any(not argument for argument in request.command):
        return WrapCommandResult(None, 2, "COMMAND_REQUIRED")
    server_id, installation_id = _identities(request)
    repository = ArtifactRepository(request.root)
    recorder = IsolatedRecorder(_RecordSink(repository))
    try:
        result = await run_stdio_command(
            request.command,
            recorder=recorder,
            server_id=server_id,
            installation_id=installation_id,
        )
    except (OSError, RuntimeError, ValueError):
        return WrapCommandResult(None, 5, "WRAP_RUNTIME_FAILED")
    return WrapCommandResult(
        result,
        result.exit_code if result.exit_code is not None else 5,
        "WRAP_COMPLETE",
    )


def run_wrap(request: WrapRequest) -> WrapCommandResult:
    return asyncio.run(_run(request))


__all__ = ["WrapCommandResult", "WrapRequest", "run_wrap"]
