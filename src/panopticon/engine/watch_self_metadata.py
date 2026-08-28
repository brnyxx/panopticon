"""Bounded, read-only acquisition of project metadata for explicit self watches."""

from __future__ import annotations

import json
import os
import tomllib
from collections.abc import Mapping
from pathlib import Path

from panopticon.probe.argument_schema import JsonValue

_MAX_README = 64 * 1024
_MAX_MANIFEST = 256 * 1024
_MAX_FILES = 512
_MAX_DEPTH = 8


def _jsonable(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    raise TypeError("non-JSON metadata")


def _read(path: Path, limit: int) -> str | None:
    try:
        if path.stat().st_size > limit or path.is_symlink():
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _parse(path: Path, limit: int, kind: str) -> JsonValue | None:
    text = _read(path, limit)
    if text is None:
        return None
    try:
        if kind == "json":
            raw: object = json.loads(text)
            return _jsonable(raw)
        if kind == "toml":
            return _jsonable(tomllib.loads(text))
        try:
            import yaml
        except ImportError:
            return text
        return _jsonable(yaml.safe_load(text))
    except (ValueError, TypeError):
        return text


def _project_files(root: Path) -> tuple[str, ...]:
    """Return only bounded, regular files whose resolved path stays in root."""
    root = root.resolve()
    found: list[str] = []
    try:
        for base, dirs, files in os.walk(root, followlinks=False):
            relative_depth = len(Path(base).relative_to(root).parts)
            dirs[:] = [
                d
                for d in dirs
                if d not in {".git", ".venv", "node_modules"} and relative_depth < _MAX_DEPTH
            ]
            for name in files:
                path = Path(base) / name
                try:
                    if (
                        not path.is_file()
                        or path.is_symlink()
                        or not path.resolve().is_relative_to(root)
                    ):
                        continue
                    found.append(path.relative_to(root).as_posix())
                except OSError:
                    continue
                if len(found) >= _MAX_FILES:
                    return tuple(sorted(found))
    except OSError:
        return ()
    return tuple(sorted(found))


def acquire_self_metadata(cwd: Path) -> dict[str, JsonValue]:
    """Acquire permitted project evidence; never returns project file contents except README."""
    root = cwd.resolve()
    result: dict[str, JsonValue] = {"project_filenames": list(_project_files(root))}
    readme = next(
        (
            root / n
            for n in ("README.md", "README.rst", "README.txt", "README")
            if (root / n).is_file()
        ),
        None,
    )
    if readme is not None:
        text = _read(readme, _MAX_README)
        result["readme"] = text if text is not None else 0
    for name, kind in (("package.json", "json"), ("pyproject.toml", "toml")):
        path = root / name
        if path.is_file():
            parsed = _parse(path, _MAX_MANIFEST, kind)
            result["manifest"] = parsed if parsed is not None else 0
            break
    config = root / ".panopticon.yaml"
    if config.is_file():
        parsed = _parse(config, _MAX_MANIFEST, "yaml")
        result["config"] = parsed if parsed is not None else 0
    return result


__all__ = ["acquire_self_metadata"]
