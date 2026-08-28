# Copyright (c) 2026 MCP Sentinel contributors
# SPDX-License-Identifier: MIT
"""Deterministic, sanitized evidence context construction."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

from pydantic import Field

from panopticon.models.common import NonEmptyStr, StrictModel
from panopticon.models.finding import Finding

REDACTED_MARKER = "<SENTINEL_REDACTED_VALUE>"
PATH_REDACTION = "<SENTINEL_ABSOLUTE_PATH:REDACTED>"
_SECRET_PATTERNS = (
    re.compile(r"\b(?:ghp_|github_pat_|sk-|xox[baprs]-)[A-Za-z0-9_-]{12,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*(?:[\"'][^\"'\r\n]{8,}[\"']|[^\s,;]{8,})"
    ),
)
_POSIX = re.compile(r"(?<![A-Za-z0-9_.-])/(?:Users|home|var|tmp|private|opt|etc)/[^\s\"'`,;]+")
_WINDOWS = re.compile(r"(?i)\b[A-Z]:\\(?:[^\\\s\"']+\\)*[^\\\s\"']+")


class ContextBlock(StrictModel):
    path: NonEmptyStr
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    text: str
    role: NonEmptyStr


class FindingContext(StrictModel):
    finding_id: str
    blocks: tuple[ContextBlock, ...]
    context_hash: NonEmptyStr

    def contains(self, path: str, start_line: int, end_line: int) -> bool:
        return any(
            b.path == path and b.start_line <= start_line <= end_line <= b.end_line
            for b in self.blocks
        )


def sanitize_text(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(REDACTED_MARKER, result)
    result = _POSIX.sub(PATH_REDACTION, _WINDOWS.sub(PATH_REDACTION, result))
    if (
        result.count("\n") != value.count("\n")
        or any(p.search(result.replace(REDACTED_MARKER, "")) for p in _SECRET_PATTERNS)
        or _POSIX.search(result)
        or _WINDOWS.search(result)
    ):
        raise ValueError("unsafe redaction")
    return result


def build_finding_context(root: Path, finding: Finding) -> FindingContext:
    location = finding.location
    if location is None:
        text = sanitize_text(
            json.dumps(
                [e.model_dump(mode="json") for e in finding.evidence],
                sort_keys=True,
                ensure_ascii=False,
                indent=2,
            )
        )
        dynamic_blocks = (
            ContextBlock(
                path=".panopticon/dynamic-evidence.json",
                start_line=1,
                end_line=max(1, len(text.splitlines())),
                text=text,
                role="dynamic_evidence",
            ),
        )
        return _finish(finding, dynamic_blocks)
    path = root / str(location.path)
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(location.path))
    except (OSError, UnicodeDecodeError, SyntaxError) as error:
        raise ValueError("CONTEXT_SOURCE_UNREADABLE") from error
    lines = source.splitlines()
    target = location.line
    units = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and n.lineno <= target <= (n.end_lineno or n.lineno)
    ]
    primary = min(units, key=lambda n: (n.end_lineno or n.lineno) - n.lineno, default=None)
    if primary is None:
        start, end = _window(target, target, len(lines), 80)
        calls: set[str] = set()
    else:
        start, end = _window(
            primary.lineno, primary.end_lineno or primary.lineno, len(lines), 80, target
        )
        calls = {
            c.func.id
            for c in ast.walk(primary)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        }
    blocks = [_block(str(location.path), lines, start, end, "primary")]
    helpers = {
        n.name: n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name in calls
        and not (n.lineno <= target <= (n.end_lineno or n.lineno))
    }
    for name in sorted(helpers)[:2]:
        n = helpers[name]
        s, e = _window(n.lineno, n.end_lineno or n.lineno, len(lines), 40)
        blocks.append(_block(str(location.path), lines, s, e, "helper"))
    if sum(b.end_line - b.start_line + 1 for b in blocks) > 160:
        raise ValueError("context exceeded safety limit")
    return _finish(finding, tuple(blocks))


def _block(path: str, lines: list[str], start: int, end: int, role: str) -> ContextBlock:
    return ContextBlock(
        path=path,
        start_line=start,
        end_line=end,
        text=sanitize_text("\n".join(lines[start - 1 : end])),
        role=role,
    )


def _finish(finding: Finding, blocks: tuple[ContextBlock, ...]) -> FindingContext:
    payload = [b.model_dump(mode="json") for b in blocks]
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return FindingContext(finding_id=str(finding.id), blocks=blocks, context_hash=digest)


def _window(
    unit_start: int, unit_end: int, count: int, limit: int, focus: int | None = None
) -> tuple[int, int]:
    if unit_end - unit_start + 1 <= limit:
        return unit_start, unit_end
    center = focus or unit_start
    start = max(unit_start, center - limit // 2)
    end = min(unit_end, start + limit - 1)
    return max(unit_start, end - limit + 1), end
