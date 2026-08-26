"""Pre-persistence leak check (AGENTS.md ground rule 4).

Every write of an observation, baseline, wrap record, log line, report, PNG, or SARIF must call
`assert_clean` first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"ghp_[A-Za-z0-9]{20,}",
        r"github_pat_[A-Za-z0-9_]{20,}",
        r"sk-ant-[A-Za-z0-9\-_]{20,}",
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


@dataclass(frozen=True)
class LeakHit:
    kind: str  # "token" | "home_path" | "real_env"
    snippet: str


class LeakError(RuntimeError):
    def __init__(self, hits: list[LeakHit]) -> None:
        super().__init__(f"refusing to persist: {len(hits)} leak(s): {[h.kind for h in hits]}")
        self.hits = hits


def find_leaks(
    text: str, *, home_paths: tuple[str, ...] = (), secrets: tuple[str, ...] = ()
) -> list[LeakHit]:
    hits: list[LeakHit] = []
    for pat in TOKEN_PATTERNS:
        hits.extend(LeakHit("token", m.group(0)[:6] + "…") for m in pat.finditer(text))
    hits.extend(LeakHit("home_path", hp) for hp in home_paths if hp and hp in text)
    hits.extend(LeakHit("real_env", s[:4] + "…") for s in secrets if s and s in text)
    return hits


def assert_clean(
    text: str, *, home_paths: tuple[str, ...] = (), secrets: tuple[str, ...] = ()
) -> None:
    hits = find_leaks(text, home_paths=home_paths, secrets=secrets)
    if hits:
        raise LeakError(hits)


def redact_token(value: str) -> str:
    """`ghp_abc…Kx2` — first 4 and last 3 characters only."""
    if len(value) <= 8:
        return "…"
    return f"{value[:4]}…{value[-3:]}"
