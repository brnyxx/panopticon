#!/usr/bin/env python3
"""Validate the exact attested platform evidence set, failing closed."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

REQUIRED = (
    "darwin-arm64",
    "darwin-x86_64",
    "linux-amd64",
    "linux-arm64",
    "windows-x64",
    "wsl2-x64",
)
_MANIFEST_KEYS = {
    "schema_version",
    "label",
    "platform",
    "commit",
    "runner",
    "fixture_version",
    "commands",
    "container",
    "orphan_result",
    "attestation",
}


def _load(path: Path) -> dict[str, object]:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("MANIFEST_NOT_OBJECT")
    return cast(dict[str, object], raw)


def _mapping(value: object, reason: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(reason)
    return cast(Mapping[str, object], value)


def _commands_valid(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(command, dict)
            and set(command) == {"argv", "exit_code", "stdout_sha256", "stderr_sha256"}
            and command.get("exit_code") == 0
            for command in value
        )
    )


def _container_valid(value: object, *, linux: bool) -> bool:
    container = _mapping(value, "CONTAINER_INVALID")
    keys = {
        "status",
        "reason_code",
        "engine",
        "privileged",
        "network_mode",
        "read_only",
        "cap_drop",
        "security_opt",
        "mounts",
        "digest",
    }
    if set(container) != keys:
        return False
    if not linux:
        return (
            container.get("status") == "UNSUPPORTED"
            and container.get("reason_code") == "PLATFORM_CONTAINER_UNSUPPORTED"
            and container.get("digest") == ""
        )
    security_opt = container.get("security_opt")
    cap_drop = container.get("cap_drop")
    digest = container.get("digest")
    return (
        container.get("status") == "running"
        and container.get("reason_code") == "CONTAINER_INSPECTED"
        and container.get("privileged") is False
        and container.get("network_mode") == "none"
        and container.get("read_only") is True
        and isinstance(cap_drop, list)
        and "ALL" in cap_drop
        and isinstance(security_opt, list)
        and any("no-new-privileges" in str(item) for item in security_opt)
        and container.get("mounts") == []
        and isinstance(digest, str)
        and digest.startswith("sha256:")
        and len(digest) == 71
    )


def _orphan_valid(value: object, *, linux: bool) -> bool:
    orphan = _mapping(value, "ORPHAN_INVALID")
    expected = "absent" if linux else "UNSUPPORTED"
    return (
        set(orphan) == {"status", "count"}
        and orphan.get("status") == expected
        and orphan.get("count") == 0
    )


def _manifest_valid(
    manifest: Mapping[str, object],
    label: str,
    commit: str | None,
) -> bool:
    platform_data = _mapping(manifest.get("platform"), "PLATFORM_INVALID")
    linux = label.startswith("linux-")
    os_name, arch = label.rsplit("-", 1)
    attestation = _mapping(manifest.get("attestation"), "ATTESTATION_INVALID")
    runner = _mapping(manifest.get("runner"), "RUNNER_INVALID")
    return (
        set(manifest) == _MANIFEST_KEYS
        and set(platform_data) == {"os", "arch"}
        and set(runner) == {"os", "arch"}
        and all(isinstance(value, str) and value for value in runner.values())
        and set(attestation) == {"status"}
        and manifest.get("schema_version") == 1
        and manifest.get("label") == label
        and platform_data.get("os") == os_name
        and platform_data.get("arch") == arch
        and (commit is None or manifest.get("commit") == commit)
        and isinstance(manifest.get("fixture_version"), str)
        and bool(manifest.get("fixture_version"))
        and _commands_valid(manifest.get("commands"))
        and _container_valid(manifest.get("container"), linux=linux)
        and _orphan_valid(manifest.get("orphan_result"), linux=linux)
        and attestation.get("status") == "verified"
    )


def _required(value: str) -> tuple[str, ...]:
    labels = tuple(part.strip() for part in value.split(",") if part.strip())
    invalid = not labels or len(set(labels)) != len(labels)
    if invalid or any(label not in REQUIRED for label in labels):
        raise ValueError("REQUIRED_LABELS_INVALID")
    return labels


def _offline_attestations(path: Path | None) -> frozenset[str]:
    if path is None:
        return frozenset()
    document = _load(path)
    return frozenset(
        label
        for label, value in document.items()
        if isinstance(value, dict) and value.get("verified") is True
    )


def _verify_github(path: Path, repo: str) -> bool:
    result = subprocess.run(
        ["gh", "attestation", "verify", str(path), "--repo", repo],
        shell=False,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def validate(
    evidence_dir: Path,
    labels: tuple[str, ...],
    *,
    commit: str | None,
    offline_attestations: frozenset[str],
    github_repo: str | None,
) -> dict[str, dict[str, object]]:
    paths = sorted(evidence_dir.glob("*.json"))
    evidence: dict[str, dict[str, object]] = {}
    for path in paths:
        manifest = _load(path)
        label = manifest.get("label")
        if not isinstance(label, str) or label not in labels or label in evidence:
            raise ValueError("DUPLICATE_OR_UNEXPECTED_MANIFEST")
        verified = label in offline_attestations or (
            github_repo is not None and _verify_github(path, github_repo)
        )
        manifest["attestation"] = {"status": "verified" if verified else "unverified"}
        if not _manifest_valid(manifest, label, commit):
            raise ValueError(f"MANIFEST_INVALID:{label}")
        evidence[label] = manifest
    missing = set(labels) - set(evidence)
    if missing:
        raise ValueError("MISSING_PLATFORMS:" + ",".join(sorted(missing)))
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require", required=True)
    parser.add_argument("--evidence-dir", type=Path, default=Path("evidence"))
    parser.add_argument("--commit")
    parser.add_argument("--attestation", type=Path)
    parser.add_argument("--github-repo")
    args = parser.parse_args()
    try:
        labels = _required(args.require)
        evidence = validate(
            args.evidence_dir,
            labels,
            commit=args.commit,
            offline_attestations=_offline_attestations(args.attestation),
            github_repo=args.github_repo,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"platform matrix rejected: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"count": len(evidence), "platforms": labels}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
