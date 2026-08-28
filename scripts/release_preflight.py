"""Fail-closed external release prerequisite preflight."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

_ACTION = re.compile(r"^\s*- uses: ([^\s]+)$", re.MULTILINE)
_SHA = re.compile(r"[^@]+@[0-9a-f]{40}$")
_REQUIRED_ENVIRONMENTS = {"pypi", "release", "testpypi"}
_REQUIRED_CHECKS = {
    "lint-type",
    "self-scan",
    "test (macos-latest, 3.11)",
    "test (macos-latest, 3.12)",
    "test (ubuntu-latest, 3.11)",
    "test (ubuntu-latest, 3.12)",
    "test-docker",
    "validate",
}


def _json_command(arguments: list[str]) -> Any:
    completed = subprocess.run(arguments, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def _required_status_checks(rulesets: list[dict[str, Any]]) -> set[str]:
    checks: set[str] = set()
    for ruleset in rulesets:
        if ruleset.get("enforcement") != "active":
            continue
        detail = _json_command(["gh", "api", str(ruleset["_links"]["self"]["href"])])
        for rule in detail.get("rules", []):
            if rule.get("type") == "required_status_checks":
                checks.update(
                    item["context"] for item in rule["parameters"]["required_status_checks"]
                )
    return checks


def evaluate(repo: str, rehearsal_run: int, root: Path) -> dict[str, object]:
    problems: list[str] = []
    repository = _json_command(["gh", "api", f"repos/{repo}"])
    if repository.get("visibility") != "public":
        problems.append("REPOSITORY_NOT_PUBLIC")
    vulnerability = _json_command(["gh", "api", f"repos/{repo}/private-vulnerability-reporting"])
    if vulnerability.get("enabled") is not True:
        problems.append("PRIVATE_VULNERABILITY_REPORTING_DISABLED")
    environments = _json_command(["gh", "api", f"repos/{repo}/environments"])
    names = {entry["name"] for entry in environments.get("environments", [])}
    if not names.issuperset(_REQUIRED_ENVIRONMENTS):
        problems.append("RELEASE_ENVIRONMENT_MISSING")
    tap = _json_command(["gh", "api", "repos/brnyxx/homebrew-tap"])
    if tap.get("visibility") != "public":
        problems.append("HOMEBREW_TAP_UNAVAILABLE")
    rulesets = _json_command(["gh", "api", f"repos/{repo}/rulesets"])
    if not _required_status_checks(rulesets).issuperset(_REQUIRED_CHECKS):
        problems.append("REQUIRED_STATUS_CHECK_MISSING")

    for name in ("release.yml", "images.yml", "platform.yml", "ci.yml", "audit.yml"):
        text = (root / ".github" / "workflows" / name).read_text(encoding="utf-8")
        if "TODO" in text or any(
            value != "./" and _SHA.fullmatch(value) is None for value in _ACTION.findall(text)
        ):
            problems.append(f"WORKFLOW_NOT_IMMUTABLE:{name}")
    rehearsal = _json_command(
        ["gh", "run", "view", str(rehearsal_run), "--json", "conclusion,headSha"]
    )
    if rehearsal.get("conclusion") != "success":
        problems.append("TESTPYPI_TRUSTED_PUBLISHER_UNVERIFIED")
    return {
        "schema_version": 1,
        "status": "PASS" if not problems else "BLOCKED",
        "repository": repo,
        "rehearsal_run": rehearsal_run,
        "rehearsal_commit": rehearsal.get("headSha"),
        "problems": sorted(problems),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--rehearsal-run", type=int, required=True)
    parser.add_argument("--twice", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    first = evaluate(args.repo, args.rehearsal_run, Path.cwd())
    if args.twice and evaluate(args.repo, args.rehearsal_run, Path.cwd()) != first:
        raise SystemExit("PREFLIGHT_DRIFT")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(first, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    raise SystemExit(0 if first["status"] == "PASS" else 3)


if __name__ == "__main__":
    main()
