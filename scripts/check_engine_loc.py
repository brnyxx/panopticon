#!/usr/bin/env python3
"""Enforce the repository-wide product source pure-LOC ceiling."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
SOURCE_ROOTS: Final = (ROOT / "src" / "panopticon",)
MAX_PURE_LOC: Final = 250


def pure_loc(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    physical_count = sum(
        1 for line in source.splitlines() if line.strip() and not line.lstrip().startswith("#")
    )
    tree = ast.parse(source, filename=str(path))
    statement_count = sum(isinstance(node, ast.stmt) for node in ast.walk(tree))
    return max(physical_count, statement_count)


def main() -> int:
    paths = tuple(
        sorted(
            path
            for source_root in SOURCE_ROOTS
            for path in source_root.rglob("*.py")
            if path.is_file()
        )
    )
    findings: list[str] = []
    for path in paths:
        try:
            count = pure_loc(path)
        except SyntaxError:
            findings.append(f"PURE_LOC_SYNTAX_ERROR {path.relative_to(ROOT)}")
        else:
            if count > MAX_PURE_LOC:
                findings.append(
                    f"PURE_LOC_EXCEEDED {path.relative_to(ROOT)}:{count}:{MAX_PURE_LOC}"
                )
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
