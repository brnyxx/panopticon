"""Typed evidence helpers for the local release gate."""

from __future__ import annotations

import hashlib
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TypedDict

Runner = Callable[..., subprocess.CompletedProcess[str]]


class CommandReceipt(TypedDict):
    name: str
    argv: list[str]
    exit_code: int
    duration_ms: int
    stdout_sha256: str
    stderr_sha256: str
    status: str


class CommandSpec(TypedDict):
    name: str
    argv: list[str]


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def command(name: str, argv: Sequence[str]) -> CommandSpec:
    return {"name": name, "argv": list(argv)}


def run_argv(
    argv: Sequence[str],
    runner: Runner = subprocess.run,
    *,
    name: str = "command",
    cwd: Path | None = None,
) -> CommandReceipt:
    started = time.perf_counter()
    completed = runner(
        list(argv),
        cwd=cwd,
        shell=False,
        capture_output=True,
        text=True,
        check=False,
    )
    duration = int((time.perf_counter() - started) * 1_000)
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    return {
        "name": name,
        "argv": list(argv),
        "exit_code": completed.returncode,
        "duration_ms": duration,
        "stdout_sha256": sha256(stdout.encode()),
        "stderr_sha256": sha256(stderr.encode()),
        "status": "PASS" if completed.returncode == 0 else "FAIL",
    }


def validate_inputs(
    inputs: Sequence[Mapping[str, object]],
    *,
    now: float | None = None,
    max_age: float = 86_400.0,
) -> None:
    current = time.time() if now is None else now
    if not inputs:
        raise ValueError("GATE_INPUTS_MISSING")
    for item in inputs:
        timestamp = item.get("timestamp")
        duration = item.get("duration_ms", 0)
        limit = item.get("limit_ms", float("inf"))
        invalid = item.get("status") != "PASS" or bool(item.get("skipped"))
        invalid = invalid or bool(item.get("leak"))
        if invalid or not isinstance(timestamp, (int, float)):
            raise ValueError("GATE_INPUT_INVALID")
        if current - float(timestamp) > max_age:
            raise ValueError("GATE_INPUT_STALE")
        if not isinstance(duration, (int, float)) or not isinstance(limit, (int, float)):
            raise ValueError("GATE_INPUT_INVALID")
        if float(duration) > float(limit):
            raise ValueError("GATE_INPUT_SLOW")


def git_command(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
    )


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def image_digests(root: Path) -> tuple[str, dict[str, str]]:
    images = (
        "pano-sandbox-base:ultragoal",
        "pano-sandbox-node:20-ultragoal",
        "pano-sandbox-node:22-ultragoal",
        "pano-sandbox-python:3.12-ultragoal",
    )
    runtime = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        cwd=root,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
    )
    if runtime.returncode != 0 or not runtime.stdout.strip():
        raise ValueError("CONTAINER_RUNTIME_UNAVAILABLE")
    digests: dict[str, str] = {}
    for image in images:
        inspected = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image],
            cwd=root,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
        )
        value = inspected.stdout.strip()
        if inspected.returncode != 0 or not value.startswith("sha256:"):
            raise ValueError("IMAGE_DIGEST_MISSING")
        digests[image] = value
    return runtime.stdout.strip(), digests


__all__ = [
    "CommandReceipt",
    "CommandSpec",
    "command",
    "git_command",
    "image_digests",
    "run_argv",
    "sha256",
    "tree_digest",
    "validate_inputs",
]
