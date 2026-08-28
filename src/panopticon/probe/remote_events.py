"""Leak-safe normalization of remote transport observations."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class RemoteEvent:
    kind: str
    op: str
    host: str | None = None
    path: str | None = None
    size: int | None = None
    sha256: str | None = None
    decoy_key: str | None = None
    names: tuple[str, ...] = ()


def origin_path(url: str) -> tuple[str, str]:
    p = urlsplit(url)
    return (p.netloc.casefold(), p.path or "/")


HeaderCollection = Mapping[str, str] | tuple[tuple[str, str], ...]


def header_names(headers: HeaderCollection) -> tuple[str, ...]:
    items = headers.items() if isinstance(headers, Mapping) else headers
    return tuple(sorted({str(key).casefold() for key, _value in items}))


def body_fingerprint(body: bytes) -> tuple[int, str]:
    return len(body), hashlib.sha256(body).hexdigest()


def plaintext_event(
    url: str,
    headers: HeaderCollection,
    body: bytes = b"",
) -> RemoteEvent:
    host, path = origin_path(url)
    return RemoteEvent(
        "plaintext_http",
        "request",
        host=host,
        path=path,
        size=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        names=header_names(headers),
    )


def net_event(url: str) -> RemoteEvent:
    host, _ = origin_path(url)
    return RemoteEvent("net", "connect", host=host)


def match_decoys(payload: bytes | str, decoys: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload
    return tuple(key for key, value in decoys if value and value in text)


def leak_events(
    payload: bytes | str, decoys: tuple[tuple[str, str], ...], sink: str
) -> tuple[RemoteEvent, ...]:
    return tuple(
        RemoteEvent("leak", "expose", decoy_key=key, path=sink)
        for key in match_decoys(payload, decoys)
    )


def redact_url(url: str) -> str:
    host, path = origin_path(url)
    return f"{host}{path}"


__all__ = [
    "RemoteEvent",
    "body_fingerprint",
    "header_names",
    "leak_events",
    "match_decoys",
    "net_event",
    "origin_path",
    "plaintext_event",
    "redact_url",
]
