# Copyright (c) 2026 MCP Sentinel contributors
# SPDX-License-Identifier: MIT
"""Deterministic requirement inputs adapted from pinned MCP-Sentinel logic."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from collections.abc import Iterable
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement

from .model import DependencyInput, DependencyReason, DependencyStatus, RequirementRecord

_ALLOWED_FLAGS = {
    "-r",
    "--requirement",
    "-c",
    "--constraint",
    "--require-hashes",
    "--no-deps",
    "--disable-pip-version-check",
}


def normalize_package_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def parse_requirements(lines: Iterable[str]) -> DependencyInput:
    records: list[RequirementRecord] = []
    diagnostics: list[str] = []
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-"):
            diagnostics.append(f"UNSUPPORTED_DIRECTIVE:{line_number}")
            continue
        try:
            parsed = Requirement(line)
        except InvalidRequirement:
            diagnostics.append(f"INVALID_REQUIREMENT:{line_number}")
            continue
        if parsed.url is not None:
            diagnostics.append(f"DIRECT_URL_PROHIBITED:{line_number}")
            continue
        records.append(
            RequirementRecord(
                normalize_package_name(parsed.name),
                str(parsed.specifier),
                str(parsed.marker) if parsed.marker is not None else None,
            )
        )
    records.sort(key=lambda item: (item.name, item.specifier, item.marker or ""))
    if diagnostics:
        return DependencyInput(
            DependencyStatus.INCOMPLETE,
            DependencyReason.INPUT_INVALID,
            tuple(records),
            diagnostics=tuple(diagnostics),
        )
    return DependencyInput(
        DependencyStatus.COMPLETE,
        DependencyReason.COMPLETED,
        tuple(records),
    )


def parse_pyproject(data: bytes) -> DependencyInput:
    try:
        document = tomllib.loads(data.decode())
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        return DependencyInput(DependencyStatus.INCOMPLETE, DependencyReason.INPUT_INVALID)
    project = document.get("project", {})
    dependencies = project.get("dependencies", []) if isinstance(project, dict) else []
    if not isinstance(dependencies, list) or not all(
        isinstance(item, str) for item in dependencies
    ):
        return DependencyInput(DependencyStatus.INCOMPLETE, DependencyReason.INPUT_INVALID)
    return parse_requirements(dependencies)


def validate_install_command(command: tuple[str, ...]) -> DependencyInput:
    if not command:
        return DependencyInput(
            DependencyStatus.UNSUPPORTED,
            DependencyReason.INSTALL_SHAPE_UNSUPPORTED,
        )
    lowered = tuple(item.casefold() for item in command)
    if any(
        item.startswith(("http://", "https://", "git+"))
        or item in {"-i", "--index-url", "--extra-index-url", "-e", "--editable", "."}
        for item in lowered
    ):
        return _unsupported_install()
    if lowered[0] in {"pip", "pip3"}:
        arguments = lowered[1:]
    elif re.fullmatch(r"python(?:3(?:\.\d+)?)?", lowered[0]) and lowered[1:3] == ("-m", "pip"):
        arguments = lowered[3:]
    else:
        return _unsupported_install()
    if not arguments or arguments[0] != "install":
        return _unsupported_install()
    index = 1
    saw_file = False
    while index < len(arguments):
        item = arguments[index]
        if item in {"-r", "--requirement", "-c", "--constraint"}:
            if index + 1 >= len(arguments) or not _relative_path(arguments[index + 1]):
                return _unsupported_install()
            saw_file = True
            index += 2
        elif item in _ALLOWED_FLAGS:
            index += 1
        else:
            return _unsupported_install()
    return (
        DependencyInput(DependencyStatus.COMPLETE, DependencyReason.COMPLETED)
        if saw_file
        else _unsupported_install()
    )


def collect_dependency_input(root: Path) -> DependencyInput:
    candidates = tuple(
        path
        for path in (root / "requirements.txt", root / "pyproject.toml")
        if path.is_file() and not path.is_symlink()
    )
    if not candidates:
        return DependencyInput(DependencyStatus.UNSUPPORTED, DependencyReason.INPUT_MISSING)
    if len(candidates) != 1:
        return DependencyInput(DependencyStatus.INCOMPLETE, DependencyReason.INPUT_AMBIGUOUS)
    source = candidates[0]
    data = source.read_bytes()
    if source.name == "requirements.txt":
        try:
            text = data.decode()
        except UnicodeDecodeError:
            return DependencyInput(
                DependencyStatus.INCOMPLETE,
                DependencyReason.INPUT_INVALID,
            )
        result = parse_requirements(text.splitlines())
    else:
        result = parse_pyproject(data)
    if result.status is not DependencyStatus.COMPLETE:
        return result
    fingerprint = hashlib.sha256(
        json.dumps(
            [(item.name, item.specifier, item.marker) for item in result.requirements],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return DependencyInput(
        result.status,
        result.reason_code,
        result.requirements,
        (source.relative_to(root).as_posix(),),
        fingerprint,
    )


def _relative_path(value: str) -> bool:
    path = Path(value)
    parts = value.replace("\\", "/").split("/")
    return bool(value) and not path.is_absolute() and ".." not in parts


def _unsupported_install() -> DependencyInput:
    return DependencyInput(
        DependencyStatus.UNSUPPORTED,
        DependencyReason.INSTALL_SHAPE_UNSUPPORTED,
    )
