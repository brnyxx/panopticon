from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import release_preflight

SHA = "a" * 40
REPO = "brnyxx/panopticon"
WORKFLOWS = ("release.yml", "images.yml", "platform.yml", "ci.yml", "audit.yml")


def _root(tmp_path: Path, release_content: str | None = None) -> Path:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    content = f"jobs:\n  build:\n    steps:\n      - uses: actions/checkout@{SHA}\n"
    for name in WORKFLOWS:
        (workflows / name).write_text(
            release_content if name == "release.yml" and release_content else content,
            encoding="utf-8",
        )
    return tmp_path


def _environment() -> dict[str, Any]:
    return {
        "deployment_branch_policy": {"protected_branches": True},
        "protection_rules": [{"type": "required_reviewers"}],
        "can_admins_bypass": False,
    }


def _responses(
    *,
    environments: dict[str, dict[str, Any]] | None = None,
    rehearsal: dict[str, Any] | None = None,
) -> tuple[Callable[[list[str]], Any], list[list[str]]]:
    environment_details = environments or {
        name: _environment() for name in release_preflight._REQUIRED_ENVIRONMENTS
    }
    run = rehearsal or {
        "conclusion": "success",
        "headBranch": "main",
        "headSha": SHA,
        "workflowName": "release",
        "event": "workflow_dispatch",
        "jobs": [
            {"name": "testpypi", "conclusion": "success"},
            {"name": "draft", "conclusion": "success"},
            {"name": "homebrew-handoff", "conclusion": "success"},
        ],
    }
    calls: list[list[str]] = []

    def command(arguments: list[str]) -> Any:
        calls.append(arguments)
        key = arguments[-1]
        if key == f"repos/{REPO}":
            return {"visibility": "public"}
        if key.endswith("private-vulnerability-reporting"):
            return {"enabled": True}
        if key.endswith("environments"):
            return {"environments": [{"name": name} for name in environment_details]}
        if "/environments/" in key:
            return environment_details[key.rsplit("/", 1)[1]]
        if key == "repos/brnyxx/homebrew-tap":
            return {"visibility": "public"}
        if key.endswith("rulesets"):
            return [{"enforcement": "active", "_links": {"self": {"href": "ruleset"}}}]
        if key == "ruleset":
            return {
                "rules": [
                    {
                        "type": "required_status_checks",
                        "parameters": {
                            "required_status_checks": [
                                {"context": item} for item in release_preflight._REQUIRED_CHECKS
                            ]
                        },
                    }
                ]
            }
        if arguments[:3] == ["gh", "run", "view"]:
            return run
        raise AssertionError(arguments)

    return command, calls


def _evaluate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    release_content: str | None = None,
    environments: dict[str, dict[str, Any]] | None = None,
    rehearsal: dict[str, Any] | None = None,
    source_sha: str = SHA,
) -> tuple[dict[str, object], list[list[str]]]:
    command, calls = _responses(environments=environments, rehearsal=rehearsal)
    monkeypatch.setattr(release_preflight, "_json_command", command)
    return (
        release_preflight.evaluate(REPO, 42, source_sha, _root(tmp_path, release_content)),
        calls,
    )


def test_preflight_accepts_exact_governance_and_rehearsal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, calls = _evaluate(tmp_path, monkeypatch)

    assert result["status"] == "PASS"
    assert result["problems"] == []
    assert calls[-1][:6] == ["gh", "run", "view", "42", "--repo", REPO]


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (
            "jobs:\n  build:\n    steps:\n"
            "      # - uses: evil/action@v1\n"
            f'      - uses: "actions/checkout@{SHA}"\n',
            None,
        ),
        ("jobs:\n  build:\n    steps:\n      - uses: ./actions/release\n", None),
        (
            f"jobs:\n  reusable:\n    uses: owner/workflow/.github/workflows/release.yml@{SHA}\n",
            None,
        ),
        (
            "jobs:\n  build:\n    steps:\n      - uses: actions/checkout@v4\n",
            "WORKFLOW_NOT_IMMUTABLE:release.yml",
        ),
        (
            "jobs:\n  reusable:\n    uses: owner/workflow/.github/workflows/release.yml@main\n",
            "WORKFLOW_NOT_IMMUTABLE:release.yml",
        ),
    ],
)
def test_preflight_parses_workflow_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: str,
    expected: str | None,
) -> None:
    result, _ = _evaluate(tmp_path, monkeypatch, release_content=content)

    assert (expected in result["problems"]) if expected else result["status"] == "PASS"


def test_preflight_rejects_malformed_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = _evaluate(tmp_path, monkeypatch, release_content="jobs: [")

    assert "WORKFLOW_PARSE_FAILED:release.yml" in result["problems"]


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"workflowName": "other"}, "REHEARSAL_WORKFLOW_MISMATCH"),
        ({"event": "push"}, "REHEARSAL_EVENT_MISMATCH"),
        ({"headBranch": "feature/release"}, "REHEARSAL_BRANCH_MISMATCH"),
        ({"headSha": "b" * 40}, "REHEARSAL_SOURCE_SHA_MISMATCH"),
        ({"conclusion": "failure"}, "REHEARSAL_CONCLUSION_NOT_SUCCESS"),
        (
            {"jobs": [{"name": "draft", "conclusion": "success"}]},
            "REHEARSAL_REQUIRED_JOB_NOT_SUCCESS:testpypi",
        ),
        (
            {"jobs": [{"name": "testpypi", "conclusion": "success"}]},
            "REHEARSAL_REQUIRED_JOB_NOT_SUCCESS:draft",
        ),
        (
            {
                "jobs": [
                    {"name": "testpypi", "conclusion": "success"},
                    {"name": "draft", "conclusion": "success"},
                ]
            },
            "REHEARSAL_REQUIRED_JOB_NOT_SUCCESS:homebrew-handoff",
        ),
    ],
)
def test_preflight_rejects_unbound_rehearsal_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: dict[str, Any],
    expected: str,
) -> None:
    rehearsal = {
        "conclusion": "success",
        "headBranch": "main",
        "headSha": SHA,
        "workflowName": "release",
        "event": "workflow_dispatch",
        "jobs": [
            {"name": "testpypi", "conclusion": "success"},
            {"name": "draft", "conclusion": "success"},
            {"name": "homebrew-handoff", "conclusion": "success"},
        ],
    }
    rehearsal.update(change)

    result, _ = _evaluate(tmp_path, monkeypatch, rehearsal=rehearsal)

    assert result["status"] == "BLOCKED"
    assert expected in result["problems"]


@pytest.mark.parametrize(
    ("name", "change", "expected"),
    [
        (
            "release",
            {"deployment_branch_policy": {"protected_branches": False}},
            "RELEASE_ENVIRONMENT_BRANCH_PROTECTION_MISSING:release",
        ),
        ("pypi", {"protection_rules": []}, "RELEASE_ENVIRONMENT_REQUIRED_REVIEWER_MISSING:pypi"),
        (
            "release",
            {"protection_rules": []},
            "RELEASE_ENVIRONMENT_REQUIRED_REVIEWER_MISSING:release",
        ),
        ("npm", {"can_admins_bypass": True}, "RELEASE_ENVIRONMENT_ADMIN_BYPASS_ALLOWED:npm"),
    ],
)
def test_preflight_rejects_incomplete_environment_governance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    change: dict[str, Any],
    expected: str,
) -> None:
    environments = {name: _environment() for name in release_preflight._REQUIRED_ENVIRONMENTS}
    environments[name].update(change)

    result, _ = _evaluate(tmp_path, monkeypatch, environments=environments)

    assert result["status"] == "BLOCKED"
    assert expected in result["problems"]


def test_preflight_rejects_missing_required_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environments = {name: _environment() for name in release_preflight._REQUIRED_ENVIRONMENTS}
    del environments["npm"]

    result, _ = _evaluate(tmp_path, monkeypatch, environments=environments)

    assert result["problems"] == ["RELEASE_ENVIRONMENT_MISSING:npm"]


def test_preflight_rejects_invalid_source_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = _evaluate(tmp_path, monkeypatch, source_sha="short")

    assert "REHEARSAL_SOURCE_SHA_INVALID" in result["problems"]
