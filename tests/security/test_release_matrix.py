"""Platform release evidence rejects missing, stale, or weakened guarantees."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
LABELS = (
    "darwin-arm64",
    "darwin-x86_64",
    "linux-amd64",
    "linux-arm64",
    "windows-x64",
    "wsl2-x64",
)


def _container(label: str) -> dict[str, object]:
    linux = label.startswith("linux-")
    return {
        "status": "running" if linux else "UNSUPPORTED",
        "reason_code": ("CONTAINER_INSPECTED" if linux else "PLATFORM_CONTAINER_UNSUPPORTED"),
        "engine": "docker",
        "privileged": False,
        "network_mode": "none" if linux else "",
        "read_only": linux,
        "cap_drop": ["ALL"] if linux else [],
        "security_opt": ["no-new-privileges"] if linux else [],
        "mounts": [],
        "digest": "sha256:" + "a" * 64 if linux else "",
    }


def manifest(label: str) -> dict[str, object]:
    os_name, arch = label.rsplit("-", 1)
    linux = label.startswith("linux-")
    return {
        "schema_version": 1,
        "label": label,
        "platform": {"os": os_name, "arch": arch},
        "commit": "abc",
        "runner": {"os": "fixture", "arch": arch},
        "fixture_version": "omo-40-v1",
        "commands": [
            {
                "argv": ["pytest", "fixture"],
                "exit_code": 0,
                "stdout_sha256": "b" * 64,
                "stderr_sha256": "c" * 64,
            }
        ],
        "container": _container(label),
        "orphan_result": {
            "status": "absent" if linux else "UNSUPPORTED",
            "count": 0,
        },
        "attestation": {"status": "unverified"},
    }


def _write_set(directory: Path, attestation: Path) -> None:
    for label in LABELS:
        (directory / f"{label}.json").write_text(
            json.dumps(manifest(label)),
            encoding="utf-8",
        )
    attestation.write_text(
        json.dumps({label: {"verified": True} for label in LABELS}),
        encoding="utf-8",
    )


def run_validator(directory: Path, attestation: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_platform_matrix.py"),
            "--require",
            ",".join(LABELS),
            "--evidence-dir",
            str(directory),
            "--commit",
            "abc",
            "--attestation",
            str(attestation),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_weakened_runtime_inspect_blocks_release(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    attestation = tmp_path / "attestations.json"
    _write_set(evidence, attestation)
    assert run_validator(evidence, attestation).returncode == 0
    cases = (
        ("privileged", True),
        ("network_mode", "host"),
        ("read_only", False),
        ("cap_drop", []),
        ("security_opt", []),
        ("mounts", ["/home/runner"]),
        ("digest", "mutable:latest"),
        ("status", "exited"),
    )
    for field, value in cases:
        item = manifest("linux-amd64")
        container = cast(dict[str, object], item["container"])
        container[field] = value
        target = evidence / "linux-amd64.json"
        target.write_text(json.dumps(item), encoding="utf-8")
        assert run_validator(evidence, attestation).returncode != 0, field
        target.write_text(json.dumps(manifest("linux-amd64")), encoding="utf-8")


def test_missing_stale_unattested_or_extra_evidence_fails(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    attestation = tmp_path / "attestations.json"
    _write_set(evidence, attestation)
    missing = evidence / "wsl2-x64.json"
    missing.unlink()
    assert run_validator(evidence, attestation).returncode != 0
    missing.write_text(json.dumps(manifest("wsl2-x64")), encoding="utf-8")

    stale = manifest("darwin-arm64")
    stale["commit"] = "old"
    target = evidence / "darwin-arm64.json"
    target.write_text(json.dumps(stale), encoding="utf-8")
    assert run_validator(evidence, attestation).returncode != 0
    target.write_text(json.dumps(manifest("darwin-arm64")), encoding="utf-8")

    attestation.write_text("{}", encoding="utf-8")
    assert run_validator(evidence, attestation).returncode != 0
    _write_set(evidence, attestation)
    leaked = manifest("linux-arm64")
    leaked["token"] = "credential-shaped-unexpected-field"
    (evidence / "linux-arm64.json").write_text(json.dumps(leaked), encoding="utf-8")
    assert run_validator(evidence, attestation).returncode != 0
