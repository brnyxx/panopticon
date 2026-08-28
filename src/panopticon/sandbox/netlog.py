"""Bounded deterministic parsers for stored DNS, proxy, and blocked-egress logs."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class NetworkLogStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class NetworkLogReason(StrEnum):
    COMPLETED = "COMPLETED"
    MALFORMED_LINE = "MALFORMED_LINE"
    OVERFLOW = "OVERFLOW"


class NetworkLogSource(StrEnum):
    DNS = "dns"
    PROXY = "proxy"
    BLOCKED_EGRESS = "blocked_egress"


@dataclass(frozen=True, slots=True)
class NetworkEvent:
    source: NetworkLogSource
    host: str
    port: int | None = None
    protocol: str | None = None
    query_type: str | None = None
    allowed: bool | None = None
    timestamp: datetime | None = None


@dataclass(frozen=True, slots=True)
class NetworkLogResult:
    events: tuple[NetworkEvent, ...]
    status: NetworkLogStatus
    reason_code: NetworkLogReason
    diagnostics: tuple[str, ...] = ()


_DNS = re.compile(r"query\[(?P<type>[^]]+)]\s+(?P<host>\S+)\s+from\s+")
_PROXY_QUOTED = re.compile(
    r'(?:Established connection to host|opensock: opening connection to)\s+"?(?P<host>[^"\s:]+)"?'
    r"(?::(?P<port>\d+))?"
)
_PROXY_CONNECT = re.compile(r"\bCONNECT\s+(?P<host>\[[^]]+]|[^\s:]+):(?P<port>\d+)\b")
_BLOCKED = re.compile(
    r"\b(?:DROP|BLOCK)\b.*?\b(?:DST|dst)=(?P<host>\S+)"
    r"(?:.*?\b(?:DPT|dpt)=(?P<port>\d+))?"
    r"(?:.*?\b(?:PROTO|proto)=(?P<protocol>[A-Za-z0-9]+))?"
)
_TINY_TIMESTAMP = re.compile(
    r"^[A-Z]+\s+(?P<stamp>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+"
)


def _clean_host(value: str) -> str:
    return value.strip().strip('"').strip("[]").rstrip(".").casefold()


def _json_event(line: str, source: NetworkLogSource) -> NetworkEvent | None:
    try:
        value: object = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, Mapping):
        return None
    raw_host = value.get("host", value.get("query", value.get("destination")))
    if not isinstance(raw_host, str) or not raw_host:
        return None
    raw_port = value.get("port")
    port = raw_port if isinstance(raw_port, int) and 0 <= raw_port <= 65535 else None
    raw_protocol = value.get("protocol")
    protocol = raw_protocol.casefold() if isinstance(raw_protocol, str) else None
    raw_query_type = value.get("query_type", value.get("qtype"))
    query_type = raw_query_type.upper() if isinstance(raw_query_type, str) else None
    raw_allowed = value.get("allowed")
    allowed = raw_allowed if isinstance(raw_allowed, bool) else None
    raw_timestamp = value.get("timestamp", value.get("time"))
    timestamp = None
    if isinstance(raw_timestamp, str):
        with suppress(ValueError):
            timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00")).astimezone(UTC)
    if source is NetworkLogSource.BLOCKED_EGRESS:
        allowed = False
    return NetworkEvent(
        source, _clean_host(raw_host), port, protocol, query_type, allowed, timestamp
    )


def _dns_event(line: str) -> NetworkEvent | None:
    if event := _json_event(line, NetworkLogSource.DNS):
        return event
    matched = _DNS.search(line)
    if matched is None:
        return None
    return NetworkEvent(
        NetworkLogSource.DNS,
        _clean_host(matched.group("host")),
        protocol="dns",
        query_type=matched.group("type").upper(),
        allowed=True,
    )


def _proxy_event(line: str) -> NetworkEvent | None:
    if event := _json_event(line, NetworkLogSource.PROXY):
        return event
    matched = _PROXY_CONNECT.search(line) or _PROXY_QUOTED.search(line)
    if matched is None:
        return None
    raw_port = matched.groupdict().get("port")
    return NetworkEvent(
        NetworkLogSource.PROXY,
        _clean_host(matched.group("host")),
        int(raw_port) if raw_port else None,
        protocol="tcp",
        allowed=True,
    )


def _blocked_event(line: str) -> NetworkEvent | None:
    if event := _json_event(line, NetworkLogSource.BLOCKED_EGRESS):
        return event
    matched = _BLOCKED.search(line)
    if matched is None:
        return None
    raw_port = matched.group("port")
    raw_protocol = matched.group("protocol")
    return NetworkEvent(
        NetworkLogSource.BLOCKED_EGRESS,
        _clean_host(matched.group("host")),
        int(raw_port) if raw_port else None,
        raw_protocol.casefold() if raw_protocol else None,
        allowed=False,
    )


def _parse(
    text: str,
    parser: Callable[[str], NetworkEvent | None],
    *,
    max_bytes: int,
    max_events: int,
) -> NetworkLogResult:
    if max_bytes < 0 or max_events < 0:
        raise ValueError("network log bounds must be non-negative")
    encoded = text.encode()
    overflow = len(encoded) > max_bytes
    if overflow:
        text = encoded[:max_bytes].decode(errors="ignore")
    events: list[NetworkEvent] = []
    malformed = False
    for line in text.splitlines():
        if not line.strip():
            continue
        timestamp = None
        prefix, separator, payload = line.partition(" ")
        if separator:
            try:
                timestamp = datetime.fromisoformat(prefix.replace("Z", "+00:00")).astimezone(UTC)
                line = payload
            except ValueError:
                pass
        if timestamp is None and (matched := _TINY_TIMESTAMP.match(line)):
            with suppress(ValueError):
                timestamp = datetime.strptime(
                    f"{datetime.now(UTC).year} {matched.group('stamp')}",
                    "%Y %b %d %H:%M:%S.%f",
                ).replace(tzinfo=UTC)
        event = parser(line)
        if event is not None and timestamp is not None:
            event = NetworkEvent(
                event.source,
                event.host,
                event.port,
                event.protocol,
                event.query_type,
                event.allowed,
                timestamp,
            )
        if event is None:
            malformed = True
            continue
        events.append(event)
        if len(events) >= max_events:
            overflow = True
            break
    events = sorted(
        set(events),
        key=lambda item: (
            item.source.value,
            item.host,
            item.port or 0,
            item.protocol or "",
            item.query_type or "",
            item.timestamp.isoformat() if item.timestamp else "",
        ),
    )
    diagnostics = tuple(
        reason.value
        for active, reason in (
            (overflow, NetworkLogReason.OVERFLOW),
            (malformed, NetworkLogReason.MALFORMED_LINE),
        )
        if active
    )
    status = (
        NetworkLogStatus.FAILED
        if malformed and not events and not overflow
        else NetworkLogStatus.PARTIAL
        if overflow or malformed
        else NetworkLogStatus.COMPLETE
    )
    reason = (
        NetworkLogReason.OVERFLOW
        if overflow
        else NetworkLogReason.MALFORMED_LINE
        if malformed
        else NetworkLogReason.COMPLETED
    )
    return NetworkLogResult(tuple(events), status, reason, diagnostics)


def parse_dns_log(
    text: str, *, max_bytes: int = 1_048_576, max_events: int = 10_000
) -> NetworkLogResult:
    return _parse(text, _dns_event, max_bytes=max_bytes, max_events=max_events)


def parse_proxy_log(
    text: str, *, max_bytes: int = 1_048_576, max_events: int = 10_000
) -> NetworkLogResult:
    return _parse(text, _proxy_event, max_bytes=max_bytes, max_events=max_events)


def parse_blocked_egress_log(
    text: str, *, max_bytes: int = 1_048_576, max_events: int = 10_000
) -> NetworkLogResult:
    return _parse(text, _blocked_event, max_bytes=max_bytes, max_events=max_events)
