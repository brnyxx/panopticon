#!/usr/bin/env python3
"""Produce deterministic, fail-closed evidence for one real platform runner."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import TypedDict

from platform_evidence import (
    CommandEvidence,
    ContainerEvidence,
    OrphanEvidence,
    probe_container,
    run_command,
)

_LABELS = {
    ("Darwin", "arm64"): "darwin-arm64",
    ("Darwin", "x86_64"): "darwin-x86_64",
    ("Linux", "x86_64"): "linux-amd64",
    ("Linux", "aarch64"): "linux-arm64",
    ("Windows", "AMD64"): "windows-x64",
}
_COMMON_NODES = (
    "tests/integration/discovery",
    "tests/unit/secrets/test_encrypted_backup.py",
    "tests/e2e/test_install.py",
    "tests/e2e/test_wrap.py",
)


class PlatformEvidence(TypedDict):
    os: str
    arch: str


class RunnerEvidence(TypedDict):
    os: str
    arch: str


class AttestationEvidence(TypedDict):
    status: str


class PlatformManifest(TypedDict):
    schema_version: int
    label: str
    platform: PlatformEvidence
    commit: str
    runner: RunnerEvidence
    fixture_version: str
    commands: list[CommandEvidence]
    container: ContainerEvidence
    orphan_result: OrphanEvidence
    attestation: AttestationEvidence


def detect_label() -> str:
    system = platform.system()
    machine = platform.machine()
    is_wsl = system == "Linux" and (
        "microsoft" in platform.release().casefold() or bool(os.getenv("WSL_INTEROP"))
    )
    if is_wsl and machine.casefold() in {"x86_64", "amd64"}:
        return "wsl2-x64"
    label = _LABELS.get((system, machine))
    if label is None and system == "Linux" and machine.casefold() == "amd64":
        label = "linux-amd64"
    if label is None:
        raise RuntimeError("UNSUPPORTED_PLATFORM")
    return label


def _commit(root: Path, requested: str) -> str:
    if requested:
        return requested
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def collect(root: Path, label: str, commit: str, fixture_version: str) -> PlatformManifest:
    nodes = list(_COMMON_NODES)
    if label.startswith(("linux-", "wsl2-")):
        nodes.append("tests/integration/test_runtime_isolation.py")
    commands = [
        run_command([sys.executable, "-m", "pytest", node, "-q"], root)
        for node in nodes
        if (root / node).exists()
    ]
    container, orphan = probe_container(root, label)
    os_name, arch = label.rsplit("-", 1)
    return {
        "schema_version": 1,
        "label": label,
        "platform": {"os": os_name, "arch": arch},
        "commit": _commit(root, commit),
        "runner": {"os": platform.system(), "arch": platform.machine()},
        "fixture_version": fixture_version,
        "commands": commands,
        "container": container,
        "orphan_result": orphan,
        "attestation": {"status": "unverified"},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--fixture-version", default="omo-40-v1")
    parser.add_argument("--commit", default=os.getenv("GITHUB_SHA", ""))
    parser.add_argument("--label")
    args = parser.parse_args()
    detected = detect_label()
    if args.label is not None and args.label != detected:
        raise SystemExit("PLATFORM_LABEL_MISMATCH")
    manifest = collect(args.root, detected, args.commit, args.fixture_version)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    return (
        0
        if manifest["commands"]
        and all(command["exit_code"] == 0 for command in manifest["commands"])
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
