"""Deterministic normalization helpers for declared values."""

from __future__ import annotations

import fnmatch
import ipaddress
import posixpath
import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}
_PUBLIC_SUFFIXES = frozenset({"com", "org", "net", "edu", "gov", "io", "co.uk", "co.kr", "com.au"})


def normalize_host(value: str) -> str:
    text = value.strip().rstrip(".").casefold()
    if text.startswith("*."):
        suffix = normalize_host(text[2:])
        return f"*.{suffix}" if suffix else ""
    try:
        return ipaddress.ip_address(text.strip("[]")).compressed.casefold()
    except ValueError:
        pass
    if not text or any(not label for label in text.split(".")):
        return ""
    try:
        normalized = ".".join(label.encode("idna").decode("ascii") for label in text.split("."))
    except UnicodeError:
        return ""
    return normalized if len(normalized) <= 253 else ""


def host_port(value: str, default_scheme: str | None = None) -> tuple[str, int | None]:
    text = value.strip()
    if "://" not in text:
        text = (default_scheme + "://" if default_scheme else "//") + text
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError:
        return "", None
    host = normalize_host(parsed.hostname or "")
    if port is None and parsed.scheme in _DEFAULT_PORTS:
        port = _DEFAULT_PORTS[parsed.scheme]
    return host, port


def normalize_port(value: int | str, scheme: str | None = None) -> int | None:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_PORTS.get(scheme or "")
    return port if 1 <= port <= 65535 else None


def normalize_path(
    value: str,
    home: str | None = None,
    *,
    case_sensitive: bool = True,
) -> str | None:
    text = value.strip().replace("\\", "/")
    if not text or "\0" in text:
        return None
    is_home = text == "~" or text.startswith("~/")
    relative = text[2:] if text.startswith("~/") else "" if text == "~" else text
    collapsed = posixpath.normpath(relative)
    if collapsed == ".." or collapsed.startswith("../"):
        return None
    if is_home:
        normalized = "~" if collapsed in {"", "."} else f"~/{collapsed}"
    elif re.fullmatch(r"[A-Za-z]:/.*", relative):
        normalized = relative[0].upper() + relative[1:]
    else:
        normalized = collapsed
    if home is not None and normalized.startswith(home.replace("\\", "/").rstrip("/") + "/"):
        normalized = "~" + normalized[len(home.replace("\\", "/").rstrip("/")) :]
    return normalized if case_sensitive else normalized.casefold()


def normalize_env(value: str) -> str | None:
    text = value.strip()
    return text if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text) else None


def normalize_process(value: str) -> str | None:
    text = PurePosixPath(value.strip().replace("\\", "/")).name.casefold()
    return text if re.fullmatch(r"[a-z0-9][a-z0-9._+-]*", text) else None


def host_matches(pattern: str, host: str) -> bool:
    normalized_pattern = normalize_host(pattern)
    normalized_host = normalize_host(host)
    if not normalized_pattern or not normalized_host:
        return False
    if normalized_pattern.startswith("*."):
        suffix = normalized_pattern[2:]
        if suffix in _PUBLIC_SUFFIXES or "." not in suffix:
            return False
        return normalized_host.endswith(f".{suffix}") and normalized_host != suffix
    return normalized_pattern == normalized_host


def path_matches(
    pattern: str,
    path: str,
    *,
    case_sensitive: bool = True,
) -> bool:
    normalized_pattern = normalize_path(pattern, case_sensitive=case_sensitive)
    normalized_path = normalize_path(path, case_sensitive=case_sensitive)
    if normalized_pattern is None or normalized_path is None:
        return False
    return fnmatch.fnmatchcase(normalized_path, normalized_pattern)
