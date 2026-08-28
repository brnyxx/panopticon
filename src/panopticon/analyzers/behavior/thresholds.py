"""Frozen thresholds used by WATCH rules."""

from __future__ import annotations

BROAD_ENUMERATION_MIN = 10
MANY_EXTERNAL_URLS_MIN = 10
_ENUMERATION_ROOTS = ("~/Documents", "~/Desktop", "~/Downloads", "/Users/", "/home/")


def is_enumeration_path(path: str) -> bool:
    normalized = path.rstrip("/")
    return any(
        normalized == root or normalized.startswith(root + "/") for root in _ENUMERATION_ROOTS
    )


def broad_enumeration_count(values: tuple[str, ...]) -> int:
    return sum(1 for value in values if is_enumeration_path(value))


def many_urls(count: int) -> bool:
    return count >= MANY_EXTERNAL_URLS_MIN
