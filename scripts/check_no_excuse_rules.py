#!/usr/bin/env python3
"""Reject nondeterministic test shortcuts and static-analysis suppressions."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Final

from check_no_excuse_rules_scope import has_call

SUPPRESSION_MARKERS: Final = (
    "# " + "no" + "qa",
    "# " + "type:" + " " + "ignore",
    "# " + "pyright:" + " " + "ignore",
)
PROHIBITED_CALLS: Final[tuple[tuple[str, str, str], ...]] = (
    ("time", "sleep", "TIME_SLEEP"),
    ("asyncio", "sleep", "ASYNCIO_SLEEP"),
    ("subprocess", "run", "SUBPROCESS_RUN"),
    ("subprocess", "call", "SUBPROCESS_CALL"),
    ("subprocess", "check_call", "SUBPROCESS_CHECK_CALL"),
    ("subprocess", "check_output", "SUBPROCESS_CHECK_OUTPUT"),
    ("subprocess", "Popen", "SUBPROCESS_POPEN"),
    ("os", "system", "OS_SYSTEM"),
)


def python_paths(path: Path) -> tuple[Path, ...]:
    if path.is_file():
        return (path,) if path.suffix == ".py" else ()
    return tuple(sorted(path.rglob("*.py")))


def violations_from_source(source: str, filename: str) -> tuple[str, ...]:
    """Analyze source text without reading or writing a file."""
    tree = ast.parse(source, filename=filename)
    findings: list[str] = []
    if any(marker in source for marker in SUPPRESSION_MARKERS):
        findings.append(f"{filename}:SUPPRESSION")
    for module, function, code in PROHIBITED_CALLS:
        if has_call(tree, module, function):
            findings.append(f"{filename}:{code}")
    return tuple(findings)


def violations(path: Path) -> tuple[str, ...]:
    return violations_from_source(path.read_text(encoding="utf-8"), str(path))


def main(arguments: tuple[str, ...]) -> int:
    paths = tuple(path for argument in arguments for path in python_paths(Path(argument)))
    findings = tuple(finding for path in paths for finding in violations(path))
    for finding in findings:
        print(f"NO_EXCUSE {finding}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(tuple(sys.argv[1:])))
