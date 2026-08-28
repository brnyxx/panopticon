"""Frozen entropy and token classifiers used by CFG rules."""

from __future__ import annotations

import math
import re
from collections import Counter

TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("github_pat", re.compile(r"github_pat_")),
    ("ghp", re.compile(r"ghp_")),
    ("anthropic", re.compile(r"sk-ant-")),
    ("openai", re.compile(r"sk-")),
    ("slack", re.compile(r"xox[abp]-")),
    ("aws", re.compile(r"AKIA")),
    ("google", re.compile(r"AIza")),
    ("gitlab", re.compile(r"glpat-")),
    ("huggingface", re.compile(r"hf_")),
    ("pypi", re.compile(r"pypi-")),
    ("npm", re.compile(r"npm_")),
    ("jwt", re.compile(r"JWT")),
)


def token_classification(value: str) -> str | None:
    for name, pattern in TOKEN_PATTERNS:
        if pattern.search(value):
            return name
    return None


def shannon_entropy(value: str) -> float:
    """Return Shannon entropy in bits per character (the frozen CFG-007 formula)."""
    if not value:
        return 0.0
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in Counter(value).values())


def high_entropy(value: str) -> bool:
    return (
        len(value) >= 20 and shannon_entropy(value) >= 3.5 and token_classification(value) is None
    )
