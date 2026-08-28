#!/usr/bin/env python3
"""Run the complete local release gate and persist sanitized command evidence."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
from pathlib import Path
from typing import TypedDict

from release_evidence import (
    CommandReceipt,
    CommandSpec,
    command,
    git_command,
    image_digests,
    run_argv,
    sha256,
    tree_digest,
    validate_inputs,
)

from panopticon.util.leak_check import LeakContext, find_leaks


class ReleaseManifest(TypedDict):
    schema_version: int
    status: str
    commit: str
    platform: str
    runtime: str
    container_runtime: str
    image_digests: dict[str, str]
    fixture_digest: str
    commands: list[CommandReceipt]
    performance_sha256: str


def build_commands(temporary: Path) -> list[CommandSpec]:
    requirements = os.fspath(temporary / "requirements.txt")
    performance = os.fspath(temporary / "performance.json")
    coverage = "--cov-report=json:" + os.fspath(temporary / "coverage.json")
    return [
        command("make-ci", ("make", "ci")),
        command("images", ("make", "images")),
        command("docker-tests", ("make", "test-docker")),
        command(
            "upstream-replay",
            (
                "uv",
                "run",
                "pytest",
                "-c",
                "tests/upstream/pytest.ini",
                "tests/upstream",
                "-q",
            ),
        ),
        command(
            "coverage-85",
            (
                "uv",
                "run",
                "pytest",
                "-m",
                "not docker and not network",
                "--cov=panopticon",
                coverage,
                "--cov-fail-under=85",
                "-q",
            ),
        ),
        command(
            "dependency-export",
            (
                "uv",
                "export",
                "--frozen",
                "--no-dev",
                "--no-emit-project",
                "--format",
                "requirements-txt",
                "--output-file",
                requirements,
            ),
        ),
        command(
            "dependency-audit",
            (
                "uvx",
                "pip-audit",
                "--requirement",
                requirements,
                "--require-hashes",
                "--disable-pip",
            ),
        ),
        command(
            "leak-security",
            (
                "uv",
                "run",
                "pytest",
                "tests/unit/test_leak_check.py",
                "tests/unit/test_leak_variants.py",
                "tests/security",
                "-q",
            ),
        ),
        command("schemas", ("uv", "run", "python", "scripts/validate_schemas.py")),
        command("rules", ("uv", "run", "python", "scripts/check_rules.py")),
        command("i18n", ("uv", "run", "python", "scripts/check_i18n.py")),
        command("phrases", ("uv", "run", "python", "scripts/check_phrases.py")),
        command("source-size", ("uv", "run", "python", "scripts/check_engine_loc.py")),
        command(
            "performance",
            ("uv", "run", "python", "scripts/performance_gate.py", "--output", performance),
        ),
    ]


def gate(root: Path, output: Path, *, clean_checkout: bool) -> ReleaseManifest:
    if not clean_checkout:
        raise ValueError("CLEAN_CHECKOUT_REQUIRED")
    status = git_command(root, "status", "--porcelain", "--untracked-files=all")
    if status.returncode != 0 or status.stdout:
        raise ValueError("CHECKOUT_DIRTY")
    revision = git_command(root, "rev-parse", "HEAD")
    commit_hash = revision.stdout.strip()
    if revision.returncode != 0 or len(commit_hash) != 40:
        raise ValueError("COMMIT_UNAVAILABLE")
    temporary = root / ".pano-release-tmp"
    if temporary.exists():
        raise ValueError("TEMPORARY_PATH_EXISTS")
    temporary.mkdir()
    receipts: list[CommandReceipt] = []
    try:
        for spec in build_commands(temporary):
            receipt = run_argv(spec["argv"], name=spec["name"], cwd=root)
            receipts.append(receipt)
            if receipt["status"] != "PASS":
                raise ValueError("RELEASE_COMMAND_FAILED:" + spec["name"])
        performance = temporary / "performance.json"
        runtime, images = image_digests(root)
        manifest: ReleaseManifest = {
            "schema_version": 1,
            "status": "PASS",
            "commit": commit_hash,
            "platform": platform.platform(),
            "runtime": platform.python_version(),
            "container_runtime": runtime,
            "image_digests": images,
            "fixture_digest": tree_digest(root / "tests/fixtures"),
            "commands": receipts,
            "performance_sha256": sha256(performance.read_bytes()),
        }
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        if find_leaks(encoded, LeakContext(home_paths=(str(Path.home()),))):
            raise ValueError("RELEASE_EVIDENCE_LEAK")
        output.parent.mkdir(parents=True, exist_ok=True)
        staged = output.with_suffix(output.suffix + ".tmp")
        staged.write_text(encoded + "\n", encoding="utf-8")
        staged.replace(output)
        return manifest
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean-checkout", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    gate(Path.cwd(), args.output, clean_checkout=args.clean_checkout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_commands", "gate", "run_argv", "validate_inputs"]
