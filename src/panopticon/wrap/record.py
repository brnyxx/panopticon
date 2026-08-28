"""JSON-RPC correlation and isolated recording helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from .framing import Frame, FrameError
from .model import AlertCandidate, Coverage, ToolSpan, WrapRecordCandidate


@dataclass(slots=True)
class _Pending:
    tool: str
    started: datetime


class Correlator:
    def __init__(self, server_id: str, installation_id: str) -> None:
        self.server_id = server_id
        self.installation_id = installation_id
        self._pending: dict[str, _Pending] = {}
        self.errors = 0

    def observe(self, frame: Frame, now: datetime) -> WrapRecordCandidate | None:
        message = frame.message
        if not isinstance(message, Mapping):
            self.errors += 1
            raise FrameError("INVALID_MESSAGE")
        ident = message.get("id")
        if ident is None:
            return None
        key = str(ident)
        method = message.get("method")
        if isinstance(method, str) and method == "tools/call":
            params = message.get("params")
            tool = "unknown"
            if isinstance(params, Mapping) and isinstance(params.get("name"), str):
                tool = str(params["name"])
            self._pending[key] = _Pending(tool, now)
            return None
        pending = self._pending.pop(key, None)
        if pending is None:
            return None
        span = ToolSpan(pending.tool, key, pending.started, now)
        return WrapRecordCandidate(
            self.server_id, self.installation_id, span, (), Coverage.COMPLETE
        )


class IsolatedRecorder:
    """Invokes a recorder while converting failures into PARTIAL coverage."""

    def __init__(self, sink: object) -> None:
        self.sink = sink
        self.failures = 0

    def record(self, candidate: WrapRecordCandidate) -> bool:
        try:
            method = self.sink.record
            method(candidate)
        except (OSError, RuntimeError, ValueError, TypeError):
            self.failures += 1
            return False
        return True


class FirstSeen:
    """In-memory detector; callers decide how candidates are persisted."""

    def __init__(self) -> None:
        self._seen_hosts: set[tuple[str, str]] = set()

    def observe(
        self, installation_id: str, host: str, process: str, now: datetime
    ) -> AlertCandidate | None:
        clean_host = host.split("/", 1)[0].split(":", 1)[0]
        clean_process = process.rsplit("/", 1)[-1]
        if not clean_host or not clean_process:
            return None
        key = (installation_id, clean_host + "\0" + clean_process)
        if key in self._seen_hosts:
            return None
        self._seen_hosts.add(key)
        return AlertCandidate(installation_id, clean_host, clean_process, now)


def parse_and_correlate(
    decoder: object, data: bytes, correlator: Correlator, now: datetime
) -> tuple[WrapRecordCandidate, ...]:
    frames = decoder.feed(data)
    records: list[WrapRecordCandidate] = []
    for frame in frames:
        record = correlator.observe(frame, now)
        if record is not None:
            records.append(record)
    return tuple(records)
