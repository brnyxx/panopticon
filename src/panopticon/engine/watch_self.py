"""Resolve an explicit project-owned MCP command for `watch --self`."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path


def _command(value: object) -> tuple[str, ...] | None:
    if isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
        return tuple(value)
    return None


def resolve_self_command(root: Path) -> tuple[str, ...] | None:
    config = root / "panopticon.toml"
    if config.is_file():
        try:
            config_payload: object = tomllib.loads(config.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            config_payload = {}
        watch = config_payload.get("watch") if isinstance(config_payload, dict) else None
        command = _command(watch.get("command")) if isinstance(watch, dict) else None
        if command is not None:
            return command
    package = root / "package.json"
    if package.is_file():
        try:
            package_payload: object = json.loads(package.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            package_payload = None
        if isinstance(package_payload, dict):
            binary = package_payload.get("bin")
            name = package_payload.get("name")
            path: object = binary
            if isinstance(binary, dict):
                path = binary.get(name) if isinstance(name, str) else None
                if path is None and len(binary) == 1:
                    path = next(iter(binary.values()))
            if (
                isinstance(path, str)
                and path
                and not Path(path).is_absolute()
                and ".." not in Path(path).parts
            ):
                return ("node", f"/self/{path}")
    return None


__all__ = ["resolve_self_command"]
