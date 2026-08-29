"""Fail-closed external release prerequisite preflight."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

_COMMIT_SHA = re.compile(r"[0-9a-fA-F]{40}")
_ACTION_SHA = re.compile(r"[^@]+@[0-9a-fA-F]{40}")
_REQUIRED_ENVIRONMENTS = {"npm", "pypi", "release", "testpypi"}
_PUBLIC_PUBLISH_ENVIRONMENTS = _REQUIRED_ENVIRONMENTS
_REHEARSAL_JOBS = {"draft", "testpypi"}
_REQUIRED_CHECKS = {
    "lint-type",
    "self-scan",
    "test (macos-latest, 3.11)",
    "test (macos-latest, 3.12)",
    "test (macos-latest, 3.13)",
    "test (macos-latest, 3.14)",
    "test (ubuntu-latest, 3.11)",
    "test (ubuntu-latest, 3.12)",
    "test (ubuntu-latest, 3.13)",
    "test (ubuntu-latest, 3.14)",
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


def _workflow_actions(workflow: object) -> list[object]:
    if not isinstance(workflow, dict):
        return []
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return []
    actions: list[object] = []
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        if "uses" in job:
            actions.append(job["uses"])
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if isinstance(step, dict) and "uses" in step:
                actions.append(step["uses"])
    return actions


def _environment_problems(repo: str, environments: dict[str, Any]) -> list[str]:
    names = {
        entry["name"]
        for entry in environments.get("environments", [])
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    problems: list[str] = []
    for name in sorted(_REQUIRED_ENVIRONMENTS):
        if name not in names:
            problems.append(f"RELEASE_ENVIRONMENT_MISSING:{name}")
            continue
        detail = _json_command(["gh", "api", f"repos/{repo}/environments/{name}"])
        policy = detail.get("deployment_branch_policy")
        if not isinstance(policy, dict) or policy.get("protected_branches") is not True:
            problems.append(f"RELEASE_ENVIRONMENT_BRANCH_PROTECTION_MISSING:{name}")
        if name not in _PUBLIC_PUBLISH_ENVIRONMENTS:
            continue
        rules = detail.get("protection_rules")
        if not isinstance(rules, list) or not any(
            isinstance(rule, dict) and rule.get("type") == "required_reviewers" for rule in rules
        ):
            problems.append(f"RELEASE_ENVIRONMENT_REQUIRED_REVIEWER_MISSING:{name}")
        if detail.get("can_admins_bypass") is not False:
            problems.append(f"RELEASE_ENVIRONMENT_ADMIN_BYPASS_ALLOWED:{name}")
    return problems


def _rehearsal_problems(rehearsal: dict[str, Any], source_sha: str) -> list[str]:
    problems: list[str] = []
    if rehearsal.get("workflowName") != "release":
        problems.append("REHEARSAL_WORKFLOW_MISMATCH")
    if rehearsal.get("event") != "workflow_dispatch":
        problems.append("REHEARSAL_EVENT_MISMATCH")
    if rehearsal.get("headSha") != source_sha:
        problems.append("REHEARSAL_SOURCE_SHA_MISMATCH")
    if rehearsal.get("conclusion") != "success":
        problems.append("REHEARSAL_CONCLUSION_NOT_SUCCESS")
    jobs = rehearsal.get("jobs")
    successful_jobs = (
        {
            job.get("name")
            for job in jobs
            if isinstance(job, dict) and job.get("conclusion") == "success"
        }
        if isinstance(jobs, list)
        else set()
    )
    for name in sorted(_REHEARSAL_JOBS - successful_jobs):
        problems.append(f"REHEARSAL_REQUIRED_JOB_NOT_SUCCESS:{name}")
    return problems


def evaluate(repo: str, rehearsal_run: int, source_sha: str, root: Path) -> dict[str, object]:
    problems: list[str] = []
    if _COMMIT_SHA.fullmatch(source_sha) is None:
        problems.append("REHEARSAL_SOURCE_SHA_INVALID")
    repository = _json_command(["gh", "api", f"repos/{repo}"])
    if repository.get("visibility") != "public":
        problems.append("REPOSITORY_NOT_PUBLIC")
    vulnerability = _json_command(["gh", "api", f"repos/{repo}/private-vulnerability-reporting"])
    if vulnerability.get("enabled") is not True:
        problems.append("PRIVATE_VULNERABILITY_REPORTING_DISABLED")
    environments = _json_command(["gh", "api", f"repos/{repo}/environments"])
    problems.extend(_environment_problems(repo, environments))
    tap = _json_command(["gh", "api", "repos/brnyxx/homebrew-tap"])
    if tap.get("visibility") != "public":
        problems.append("HOMEBREW_TAP_UNAVAILABLE")
    rulesets = _json_command(["gh", "api", f"repos/{repo}/rulesets"])
    if not _required_status_checks(rulesets).issuperset(_REQUIRED_CHECKS):
        problems.append("REQUIRED_STATUS_CHECK_MISSING")

    for name in ("release.yml", "images.yml", "platform.yml", "ci.yml", "audit.yml"):
        text = (root / ".github" / "workflows" / name).read_text(encoding="utf-8")
        try:
            workflow = yaml.safe_load(text)
        except yaml.YAMLError:
            problems.append(f"WORKFLOW_PARSE_FAILED:{name}")
            continue
        if "TODO" in text or any(
            not isinstance(value, str)
            or (not value.startswith("./") and _ACTION_SHA.fullmatch(value) is None)
            for value in _workflow_actions(workflow)
        ):
            problems.append(f"WORKFLOW_NOT_IMMUTABLE:{name}")
    rehearsal = _json_command(
        [
            "gh",
            "run",
            "view",
            str(rehearsal_run),
            "--repo",
            repo,
            "--json",
            "conclusion,headSha,workflowName,event,jobs",
        ]
    )
    problems.extend(_rehearsal_problems(rehearsal, source_sha))
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
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--twice", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    first = evaluate(args.repo, args.rehearsal_run, args.source_sha, Path.cwd())
    if args.twice and evaluate(args.repo, args.rehearsal_run, args.source_sha, Path.cwd()) != first:
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
