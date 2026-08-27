"""Deterministic value-free leak detection for the persistence boundary."""

from __future__ import annotations

import base64
import binascii
import json
import re
import shlex
from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import PurePosixPath
from typing import Final
from urllib.parse import quote, quote_plus, unquote, unquote_plus

TOKEN_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(pattern)
    for pattern in (
        r"ghp_[A-Za-z0-9]{20,}",
        r"github_pat_[A-Za-z0-9_]{20,}",
        r"sk-ant-[A-Za-z0-9\-_]{20,}",
        r"sk-proj-[A-Za-z0-9\-_]{20,}",
        r"sk-[A-Za-z0-9]{20,}",
        r"xox[abp]-[A-Za-z0-9\-]{10,}",
        r"AKIA[0-9A-Z]{16}",
        r"AIza[0-9A-Za-z\-_]{30,}",
        r"glpat-[A-Za-z0-9\-_]{20,}",
        r"hf_[A-Za-z0-9]{20,}",
        r"pypi-[A-Za-z0-9\-_]{20,}",
        r"npm_[A-Za-z0-9]{30,}",
        r"eyJ[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}",
    )
)
_CHUNK_MARKERS: Final[re.Pattern[str]] = re.compile(r'""|\'\'|\\\r?\n')
_BASE64_CANDIDATE: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9+/_-])"
    r"(?P<candidate>[A-Za-z0-9+/_-]{8,}(?:={1,2})?)"
    r"(?![A-Za-z0-9+/=_-])"
)
_MAX_BASE64_CANDIDATE_CHARS: Final = 4096
_MAX_BASE64_DECODED_BYTES: Final = 3072
_MAX_BASE64_DEPTH: Final = 1
_MAX_BASE64_CANDIDATES_PER_VIEW: Final = 256


@unique
class LeakReason(StrEnum):
    CREDENTIAL_PATTERN = "CREDENTIAL_PATTERN"
    REAL_ENV_VALUE = "REAL_ENV_VALUE"
    REAL_HOME = "REAL_HOME"


@unique
class LeakVariant(StrEnum):
    DIRECT = "DIRECT"
    JSON_ESCAPED = "JSON_ESCAPED"
    SHELL_ESCAPED = "SHELL_ESCAPED"
    URL_ENCODED = "URL_ENCODED"
    FORM_ENCODED = "FORM_ENCODED"
    BASE64 = "BASE64"
    BASE64_URLSAFE = "BASE64_URLSAFE"
    NATIVE_PATH = "NATIVE_PATH"
    CHUNKED = "CHUNKED"


@dataclass(frozen=True, slots=True)
class _DecodedView:
    text: str
    variant: LeakVariant


@dataclass(frozen=True, slots=True)
class LeakContext:
    """Values that must never cross one persistence boundary."""

    home_paths: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LeakHit:
    """A stable classification that intentionally contains no matched value."""

    reason: LeakReason
    variant: LeakVariant
    offset: int


@dataclass(frozen=True, slots=True)
class LeakError(RuntimeError):
    hits: tuple[LeakHit, ...]

    def __str__(self) -> str:
        classes = ",".join(f"{hit.reason}:{hit.variant}" for hit in self.hits)
        return f"refusing to persist: {len(self.hits)} leak(s) [{classes}]"


def _encoded_variants(value: str) -> tuple[tuple[str, LeakVariant], ...]:
    raw = value.encode("utf-8")
    standard = base64.b64encode(raw).decode("ascii")
    urlsafe = base64.urlsafe_b64encode(raw).decode("ascii")
    return (
        (value, LeakVariant.DIRECT),
        (json.dumps(value, ensure_ascii=True)[1:-1], LeakVariant.JSON_ESCAPED),
        (shlex.quote(value), LeakVariant.SHELL_ESCAPED),
        (quote(value, safe=""), LeakVariant.URL_ENCODED),
        (quote_plus(value, safe=""), LeakVariant.FORM_ENCODED),
        (standard, LeakVariant.BASE64),
        (standard.rstrip("="), LeakVariant.BASE64),
        (urlsafe, LeakVariant.BASE64_URLSAFE),
        (urlsafe.rstrip("="), LeakVariant.BASE64_URLSAFE),
    )


def _home_aliases(home: str) -> tuple[str, ...]:
    normalized = home.replace("\\", "/").rstrip("/")
    username = PurePosixPath(normalized).name
    if not username:
        return (home,)
    return (
        home,
        f"/home/{username}",
        f"/Users/{username}",
        f"C:/Users/{username}",
        f"C:\\Users\\{username}",
        f"\\\\server\\Users\\{username}",
        f"/mnt/c/Users/{username}",
        f"\\\\wsl.localhost\\Ubuntu\\home\\{username}",
    )


def _decoded_views(text: str) -> tuple[_DecodedView, ...]:
    escape_views = [text]
    unescaped = text
    for _ in range(3):
        unescaped = unescaped.replace("\\\\", "\\").replace('\\"', '"')
        escape_views.append(unescaped)
    views: list[_DecodedView] = []
    seen: set[str] = set()
    for index, view in enumerate(escape_views):
        escaped_variant = LeakVariant.DIRECT if index == 0 else LeakVariant.JSON_ESCAPED
        for candidate, variant in (
            (view, escaped_variant),
            (unquote(view), LeakVariant.URL_ENCODED),
            (unquote_plus(view), LeakVariant.FORM_ENCODED),
            (_CHUNK_MARKERS.sub("", view), LeakVariant.CHUNKED),
        ):
            if candidate in seen:
                continue
            seen.add(candidate)
            views.append(_DecodedView(candidate, variant))
    return tuple(views)


def _decode_base64_candidate(candidate: str) -> _DecodedView | None:
    if len(candidate) > _MAX_BASE64_CANDIDATE_CHARS:
        return None
    padded = f"{candidate}{'=' * (-len(candidate) % 4)}"
    is_urlsafe = "-" in candidate or "_" in candidate
    try:
        raw = base64.b64decode(
            padded,
            altchars=b"-_" if is_urlsafe else None,
            validate=True,
        )
    except binascii.Error:
        return None
    if len(raw) > _MAX_BASE64_DECODED_BYTES:
        return None
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    variant = LeakVariant.BASE64_URLSAFE if is_urlsafe else LeakVariant.BASE64
    return _DecodedView(decoded, variant)


def _scannable_views(text: str) -> tuple[_DecodedView, ...]:
    views = list(_decoded_views(text))
    frontier = tuple(views)
    seen = {(view.text, view.variant) for view in views}
    for _ in range(_MAX_BASE64_DEPTH):
        next_frontier: list[_DecodedView] = []
        for source in frontier:
            for index, match in enumerate(_BASE64_CANDIDATE.finditer(source.text)):
                if index >= _MAX_BASE64_CANDIDATES_PER_VIEW:
                    break
                decoded = _decode_base64_candidate(match.group("candidate"))
                if decoded is None:
                    continue
                key = (decoded.text, decoded.variant)
                if key in seen:
                    continue
                seen.add(key)
                next_frontier.append(decoded)
        views.extend(next_frontier)
        frontier = tuple(next_frontier)
    return tuple(views)


def _native_home_hits(text: str, home: str) -> tuple[LeakHit, ...]:
    username = PurePosixPath(home.replace("\\", "/").rstrip("/")).name
    if not username:
        return ()
    escaped = re.escape(username)
    patterns = (
        rf"(?:[a-z]:[\\/]+users[\\/]+{escaped})(?:[\\/]|$)",
        rf"(?:/mnt/[a-z]/users/{escaped})(?:/|$)",
        rf"(?:\\\\[^\\]+\\[^\\]+\\users\\{escaped})(?:\\|$)",
        rf"(?:\\\\wsl\.localhost\\[^\\]+\\home\\{escaped})(?:\\|$)",
    )
    hits: list[LeakHit] = []
    for view in _scannable_views(text):
        variant = LeakVariant.NATIVE_PATH if view.variant is LeakVariant.DIRECT else view.variant
        for pattern in patterns:
            hits.extend(
                LeakHit(LeakReason.REAL_HOME, variant, match.start())
                for match in re.finditer(pattern, view.text, flags=re.IGNORECASE)
            )
    return tuple(hits)


def _value_hits(
    text: str, value: str, reason: LeakReason, native_path: bool = False
) -> tuple[LeakHit, ...]:
    hits: list[LeakHit] = []
    views = _decoded_views(text)
    for candidate, variant in _encoded_variants(value):
        for view in views:
            offset = view.text.find(candidate)
            if offset >= 0:
                selected = variant
                if variant is LeakVariant.DIRECT and view.variant is not LeakVariant.DIRECT:
                    selected = view.variant
                if native_path and selected is LeakVariant.DIRECT:
                    selected = LeakVariant.NATIVE_PATH
                if view.variant is LeakVariant.CHUNKED:
                    selected = LeakVariant.CHUNKED
                hits.append(LeakHit(reason, selected, offset))
    return tuple(hits)


def find_leaks(text: str, context: LeakContext | None = None) -> tuple[LeakHit, ...]:
    """Return deterministic, value-free classifications for one logical artifact."""
    active_context = context if context is not None else LeakContext()
    hits: list[LeakHit] = []
    for view in _scannable_views(text):
        for pattern in TOKEN_PATTERNS:
            hits.extend(
                LeakHit(LeakReason.CREDENTIAL_PATTERN, view.variant, match.start())
                for match in pattern.finditer(view.text)
            )
    for secret in active_context.secrets:
        if secret:
            hits.extend(_value_hits(text, secret, LeakReason.REAL_ENV_VALUE))
    for home in active_context.home_paths:
        if home:
            for alias in _home_aliases(home):
                hits.extend(_value_hits(text, alias, LeakReason.REAL_HOME, native_path=True))
            hits.extend(_native_home_hits(text, home))
    return tuple(sorted(set(hits), key=lambda hit: (hit.offset, hit.reason, hit.variant)))


def find_leaks_chunks(
    chunks: tuple[str, ...], context: LeakContext | None = None
) -> tuple[LeakHit, ...]:
    """Scan a logical stream after reconstructing all chunk boundaries."""
    return find_leaks("".join(chunks), context)


def assert_clean(text: str, context: LeakContext | None = None) -> None:
    """Raise a typed leak error before any persistence operation begins."""
    hits = find_leaks(text, context)
    if hits:
        raise LeakError(hits)


def redact_token(value: str) -> str:
    """Return first four and last three characters without exposing the middle."""
    if len(value) <= 8:
        return "…"
    return f"{value[:4]}…{value[-3:]}"
