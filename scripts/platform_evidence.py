"""Typed command and container evidence helpers for the platform matrix."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TypedDict, cast

from panopticon.util.leak_check import LeakContext, find_leaks


class CommandEvidence(TypedDict):
    argv: list[str]
    exit_code: int
    stdout_sha256: str
    stderr_sha256: str


class ContainerEvidence(TypedDict):
    status: str
    reason_code: str
    engine: str
    privileged: bool
    network_mode: str
    read_only: bool
    cap_drop: list[str]
    security_opt: list[str]
    mounts: list[str]
    digest: str


class OrphanEvidence(TypedDict):
    status: str
    count: int


def run_command(argv: list[str], root: Path) -> CommandEvidence:
    try:
        completed = subprocess.run(
            argv,
            cwd=root,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return {
            "argv": argv,
            "exit_code": 127,
            "stdout_sha256": "",
            "stderr_sha256": "",
        }
    if completed.returncode:
        diagnostic = (completed.stdout + completed.stderr)[-8_000:]
        homes = tuple(value for key in ("HOME", "USERPROFILE") if (value := os.getenv(key)))
        if not find_leaks(diagnostic, LeakContext(home_paths=homes)):
            sys.stderr.write(diagnostic)
    return {
        "argv": argv,
        "exit_code": completed.returncode,
        "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(completed.stderr.encode()).hexdigest(),
    }


def _unsupported(reason_code: str, engine: str) -> ContainerEvidence:
    return {
        "status": "UNSUPPORTED",
        "reason_code": reason_code,
        "engine": engine,
        "privileged": False,
        "network_mode": "",
        "read_only": False,
        "cap_drop": [],
        "security_opt": [],
        "mounts": [],
        "digest": "",
    }


def _inspect_payload(text: str) -> tuple[dict[str, object], dict[str, object]]:
    raw: object = json.loads(text)
    if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], dict):
        raise ValueError("INSPECT_INVALID")
    document = cast(dict[str, object], raw[0])
    host = document.get("HostConfig")
    if not isinstance(host, dict):
        raise ValueError("INSPECT_INVALID")
    return document, cast(dict[str, object], host)


def _mount_sources(document: dict[str, object]) -> list[str]:
    raw = document.get("Mounts", [])
    if not isinstance(raw, list):
        raise ValueError("INSPECT_INVALID")
    sources: list[str] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("Source"), str):
            raise ValueError("INSPECT_INVALID")
        sources.append(cast(str, item["Source"]))
    return sorted(sources)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("INSPECT_INVALID")
    return sorted(cast(list[str], value))


def probe_container(root: Path, label: str) -> tuple[ContainerEvidence, OrphanEvidence]:
    engine = os.getenv("CONTAINER_ENGINE", "docker")
    if not label.startswith("linux-"):
        return _unsupported("PLATFORM_CONTAINER_UNSUPPORTED", engine), {
            "status": "UNSUPPORTED",
            "count": 0,
        }
    name = f"pano-platform-{os.getpid()}"
    image = os.getenv("PANO_PROBE_IMAGE", "pano-sandbox-base:ultragoal")
    temporary_mount = "/" + "tmp:rw,noexec,nosuid,size=16m"
    argv = [
        engine,
        "run",
        "-d",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "256m",
        "--cpus",
        "1",
        "--pids-limit",
        "128",
        "--tmpfs",
        temporary_mount,
        image,
        "sleep",
        "60",
    ]
    evidence = _unsupported("CONTAINER_START_FAILED", engine)
    try:
        started = subprocess.run(argv, cwd=root, shell=False, check=False, capture_output=True)
        if started.returncode == 0:
            inspected = subprocess.run(
                [engine, "inspect", name],
                shell=False,
                check=False,
                capture_output=True,
                text=True,
            )
            if inspected.returncode != 0:
                evidence = _unsupported("CONTAINER_INSPECT_FAILED", engine)
            else:
                document, host = _inspect_payload(inspected.stdout)
                state = document.get("State")
                if not isinstance(state, dict):
                    raise ValueError("INSPECT_INVALID")
                evidence = {
                    "status": str(state.get("Status", "")),
                    "reason_code": "CONTAINER_INSPECTED",
                    "engine": engine,
                    "privileged": bool(host.get("Privileged", False)),
                    "network_mode": str(host.get("NetworkMode", "")),
                    "read_only": bool(host.get("ReadonlyRootfs", False)),
                    "cap_drop": _string_list(host.get("CapDrop", [])),
                    "security_opt": _string_list(host.get("SecurityOpt", [])),
                    "mounts": _mount_sources(document),
                    "digest": str(document.get("Image", "")),
                }
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        evidence = _unsupported("CONTAINER_INSPECT_INVALID", engine)
    finally:
        subprocess.run(
            [engine, "rm", "-f", name],
            shell=False,
            check=False,
            capture_output=True,
        )
    orphan = subprocess.run(
        [engine, "inspect", name],
        shell=False,
        check=False,
        capture_output=True,
    )
    orphan_count = 0 if orphan.returncode != 0 else 1
    return evidence, {
        "status": "absent" if orphan_count == 0 else "present",
        "count": orphan_count,
    }


__all__ = [
    "CommandEvidence",
    "ContainerEvidence",
    "OrphanEvidence",
    "probe_container",
    "run_command",
]
