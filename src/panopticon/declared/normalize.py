"""Deterministic normalization helpers for declared values."""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from urllib.parse import urlsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_host(value: str) -> str:
    text = value.strip().rstrip(".").lower()
    if text.startswith("*."):
        return "*." + normalize_host(text[2:])
    try:
        return ipaddress.ip_address(text.strip("[]")).compressed.lower()
    except ValueError:
        pass
    try:
        return ".".join(label.encode("idna").decode("ascii") for label in text.split("."))
    except UnicodeError:
        return text


def host_port(value: str, default_scheme: str | None = None) -> tuple[str, int | None]:
    text = value.strip()
    if "://" not in text and not text.startswith("["):
        text = (default_scheme + "://" if default_scheme else "//") + text
    parsed = urlsplit(text)
    host = parsed.hostname or ""
    port = parsed.port
    if port is None and parsed.scheme in _DEFAULT_PORTS:
        port = _DEFAULT_PORTS[parsed.scheme]
    return normalize_host(host), port


def normalize_port(value: int | str, scheme: str | None = None) -> int | None:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_PORTS.get(scheme or "")
    return port if 1 <= port <= 65535 else None


def normalize_path(value: str, home: str | Path | None = None) -> str | None:
    text = value.strip().replace("\\", "/")
    root = Path(home or Path.home()).expanduser().resolve()
    if text.startswith("~"):
        candidate = root / text[2:] if text.startswith("~/") else root
    elif text.startswith("/"):
        candidate = Path(text)
    else:
        candidate = Path(text)
    try:
        resolved = candidate.expanduser().resolve(strict=False)
    except OSError:
        return None
    if text.startswith("~"):
        try:
            resolved.relative_to(root)
        except ValueError:
            return None
        return "~/" + str(resolved.relative_to(root)).replace("\\", "/")
    return str(resolved).replace("\\", "/")


def normalize_env(value: str) -> str | None:
    text = value.strip()
    return text if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text) else None


def normalize_process(value: str) -> str | None:
    text = Path(value.strip()).name.lower()
    return text if re.fullmatch(r"[a-z0-9][a-z0-9._+-]*", text) else None


def host_matches(pattern: str, host: str) -> bool:
    p, h = normalize_host(pattern), normalize_host(host)
    if p.startswith("*."):
        return h.endswith("." + p[2:]) and h.count(".") >= p.count(".")
    return p == h


def path_matches(pattern: str, path: str) -> bool:
    import fnmatch

    p = normalize_path(pattern) or pattern
    return fnmatch.fnmatchcase(path.replace("\\", "/"), p.replace("\\", "/"))
