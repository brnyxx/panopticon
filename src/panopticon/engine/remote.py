"""Engine boundary for client-visible remote MCP observations."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from panopticon.probe.remote import RemoteObserver, RemoteRequest, RemoteResult, RemoteStatus


class CoverageStatus(StrEnum):
    COMPLETE = "COMPLETE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class RemoteCoverage:
    file: CoverageStatus = CoverageStatus.UNSUPPORTED
    process: CoverageStatus = CoverageStatus.UNSUPPORTED
    net: CoverageStatus = CoverageStatus.COMPLETE


@dataclass(frozen=True, slots=True)
class RemoteEngineResult:
    status: RemoteStatus
    reason_code: str
    result: RemoteResult
    coverage: RemoteCoverage = RemoteCoverage()


class Clock(Protocol):
    def monotonic(self) -> float: ...


class RemoteEngine:
    """Thin orchestration layer; persistence remains owned by callers/stores."""

    def __init__(self, observer: RemoteObserver) -> None:
        self.observer = observer

    def run(self, request: RemoteRequest) -> RemoteEngineResult:
        result = self.observer.observe(request)
        return RemoteEngineResult(result.status, result.reason_code, result)

    def observe_file(self, _path: str) -> RemoteEngineResult:
        result = RemoteResult(RemoteStatus.UNSUPPORTED, "REMOTE_FILE_UNSUPPORTED")
        return RemoteEngineResult(result.status, result.reason_code, result)

    def observe_process(self, _argv: tuple[str, ...]) -> RemoteEngineResult:
        result = RemoteResult(RemoteStatus.UNSUPPORTED, "REMOTE_PROCESS_UNSUPPORTED")
        return RemoteEngineResult(result.status, result.reason_code, result)


__all__ = ["CoverageStatus", "RemoteCoverage", "RemoteEngineResult", "Clock", "RemoteEngine"]
