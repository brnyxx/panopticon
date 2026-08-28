# Copyright (c) 2026 MCP Sentinel contributors
# SPDX-License-Identifier: MIT
"""Boundary-safe deterministic static file traversal."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import yaml
from pathspec import GitIgnoreSpec

from .model import ParsedPythonFile, ReportWarning, StaticFileSet

MAX_STATIC_FILE_BYTES = 1024 * 1024
_CONFIG_SUFFIXES = {".json", ".yaml", ".yml", ".toml"}
_DEFAULT_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
}


def collect_static_files(root: Path, ignore_paths: tuple[str, ...]) -> StaticFileSet:
    python_files: list[ParsedPythonFile] = []
    config_files: list[Path] = []
    ignored = 0
    symlinks: list[str] = []
    specs: dict[Path, GitIgnoreSpec] = {}
    configured = GitIgnoreSpec.from_lines(ignore_paths)

    def visit(directory: Path) -> None:
        nonlocal ignored
        gitignore = directory / ".gitignore"
        if gitignore.is_file() and not gitignore.is_symlink():
            specs[directory] = _read_gitignore(gitignore)
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as error:
            raise OSError(f"cannot traverse target directory: {directory}") from error
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            if entry.is_symlink():
                ignored += 1
                symlinks.append(relative)
                continue
            if entry.is_dir(follow_symlinks=False):
                if entry.name in _DEFAULT_DIRS or _is_ignored(
                    relative + "/", path, root, specs, configured
                ):
                    continue
                visit(path)
                continue
            if (
                not entry.is_file(follow_symlinks=False)
                or not _is_supported(path)
                or _is_ignored(relative, path, root, specs, configured)
            ):
                if entry.is_file(follow_symlinks=False) and _is_supported(path):
                    ignored += 1
                continue
            source = _read_supported(path)
            if path.suffix == ".py":
                try:
                    tree = ast.parse(source, filename=relative)
                except SyntaxError as error:
                    raise ValueError(
                        f"cannot parse Python source {relative}: {error.msg}"
                    ) from error
                python_files.append(ParsedPythonFile(path, relative, source, tree))
            else:
                _validate_config(path, relative, source)
                config_files.append(path)

    visit(root)
    suffix = ", ..." if len(symlinks) > 20 else ""
    warnings = (
        ()
        if not symlinks
        else (
            ReportWarning(
                "static_symlinks_skipped",
                f"Skipped {len(symlinks)} symlink entries: {', '.join(symlinks[:20])}{suffix}",
            ),
        )
    )
    return StaticFileSet(
        tuple(python_files),
        tuple(config_files),
        len(python_files) + len(config_files),
        ignored,
        warnings,
    )


def _is_supported(path: Path) -> bool:
    return (
        path.suffix == ".py"
        or path.suffix in _CONFIG_SUFFIXES
        or path.name == ".env"
        or path.name.startswith(".env.")
    )


def _read_supported(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError as error:
        raise OSError(f"cannot stat supported file: {path.name}") from error
    if size > MAX_STATIC_FILE_BYTES:
        raise ValueError(f"supported file exceeds 1 MiB limit: {path.name}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"supported file is not valid UTF-8: {path.name}") from error
    except OSError as error:
        raise OSError(f"cannot read supported file: {path.name}") from error


def _read_gitignore(path: Path) -> GitIgnoreSpec:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise OSError(f"cannot read .gitignore: {path}") from error
    return GitIgnoreSpec.from_lines(content.splitlines())


def _is_ignored(
    relative: str,
    path: Path,
    root: Path,
    specs: dict[Path, GitIgnoreSpec],
    configured: GitIgnoreSpec,
) -> bool:
    ignored = False
    for directory in reversed((path.parent, *path.parents)):
        if directory == root.parent:
            continue
        try:
            directory.relative_to(root)
        except ValueError:
            continue
        spec = specs.get(directory)
        if spec is not None:
            scoped = path.relative_to(directory).as_posix()
            scoped += "/" if relative.endswith("/") and not scoped.endswith("/") else ""
            result = spec.check_file(scoped)
            if result.include is not None:
                ignored = result.include
    return configured.match_file(relative) or ignored


def _validate_config(path: Path, relative: str, source: str) -> None:
    try:
        if path.suffix == ".json":
            json.loads(source)
        elif path.suffix in {".yaml", ".yml"}:
            yaml.safe_load(source)
        elif path.suffix == ".toml":
            import tomllib

            tomllib.loads(source)
        else:
            _validate_dotenv(source)
    except (json.JSONDecodeError, yaml.YAMLError, ValueError) as error:
        raise ValueError(f"cannot parse configuration {relative}: {error}") from error


def _validate_dotenv(source: str) -> None:
    for number, raw in enumerate(source.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line or not line.split("=", 1)[0].strip().isidentifier():
            raise ValueError(f"invalid dotenv syntax on line {number}")
