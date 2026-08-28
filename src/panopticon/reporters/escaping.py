"""Escaping helpers for untrusted report values."""

from __future__ import annotations

import posixpath
import re
from urllib.parse import quote


def markdown(value: object) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = text.replace("\\", "\\\\")
    return re.sub(r"([`*_{}\[\]()#+.!|<>])", r"\\\1", text)


def html(value: object) -> str:
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def artifact_uri(path: object) -> str:
    """Return a safe, repository-relative SARIF artifact URI."""
    raw = str(path).replace("\\", "/")
    if not raw or raw.startswith(("/", "//")) or re.match(r"^[A-Za-z]:[/]", raw):
        return "unknown"
    normalized = posixpath.normpath(raw)
    if normalized in (".", "") or normalized == ".." or normalized.startswith("../"):
        return "unknown"
    return quote(normalized, safe="/-._~")


__all__ = ["artifact_uri", "html", "markdown"]
