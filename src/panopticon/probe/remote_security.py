"""SSRF-safe URL and redirect validation for remote probes."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit


class Resolver(Protocol):
    def resolve(self, host: str) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class SecurityDecision:
    allowed: bool
    reason: str
    url: str
    transport_url: str = field(default="", repr=False)


_BLOCKED_NAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata.amazonaws.com",
        "instance-data.ec2.internal",
    }
)


def _blocked_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not ip.is_global


def validate_url(url: str, resolver: Resolver | None = None) -> SecurityDecision:
    try:
        p = urlsplit(url)
    except ValueError:
        return SecurityDecision(False, "INVALID_URL", "")
    if p.scheme.casefold() not in {"http", "https"}:
        return SecurityDecision(False, "SCHEME_BLOCKED", "")
    if p.username is not None or p.password is not None or p.fragment:
        return SecurityDecision(False, "CREDENTIALS_OR_FRAGMENT", "")
    host = (p.hostname or "").rstrip(".").casefold()
    if not host or host in _BLOCKED_NAMES or host.endswith(".internal"):
        return SecurityDecision(False, "HOST_BLOCKED", "")
    try:
        port = p.port or (443 if p.scheme.casefold() == "https" else 80)
    except ValueError:
        return SecurityDecision(False, "INVALID_PORT", "")
    addresses = resolver.resolve(host) if resolver is not None else (host,)
    if any(_blocked_ip(address) for address in addresses):
        return SecurityDecision(False, "ADDRESS_BLOCKED", "")
    normalized = urlunsplit(
        (p.scheme.casefold(), f"{host}:{port}" if p.port else host, p.path or "/", "", "")
    )
    return SecurityDecision(True, "OK", normalized, urlunsplit(p))


def same_origin(a: str, b: str) -> bool:
    pa, pb = urlsplit(a), urlsplit(b)
    return (
        pa.scheme.casefold(),
        pa.hostname,
        pa.port or (443 if pa.scheme == "https" else 80),
    ) == (pb.scheme.casefold(), pb.hostname, pb.port or (443 if pb.scheme == "https" else 80))


__all__ = ["Resolver", "SecurityDecision", "same_origin", "validate_url"]
