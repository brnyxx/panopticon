"""GitHub workflow files must remain parseable and structurally release-safe."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda path: path.name)
def test_every_github_workflow_is_valid_yaml(workflow: Path) -> None:
    # Given: one checked-in GitHub workflow file
    # When: PyYAML parses it with scalar-preserving BaseLoader
    document = yaml.load(workflow.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    # Then: the workflow is a YAML mapping
    assert isinstance(document, dict)


def test_release_workflow_is_tag_only_with_build_and_publish_jobs() -> None:
    # Given: the release workflow parsed without YAML 1.1 coercion of the on key
    document = yaml.load(
        (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert isinstance(document, dict)
    trigger = document["on"]
    assert isinstance(trigger, dict)
    push = trigger["push"]
    assert isinstance(push, dict)
    # When: its trigger and job structure are inspected
    # Then: only v* tags trigger the workflow, with both release jobs present
    assert set(trigger) == {"push"}
    assert set(push) == {"tags"}
    assert push["tags"] == ["v*"]
    jobs = document["jobs"]
    assert isinstance(jobs, dict)
    assert {"build", "publish"}.issubset(jobs)


def test_ci_self_scan_uses_trusted_local_action_and_pinned_upload() -> None:
    document = yaml.load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert isinstance(document, dict)
    trigger = document["on"]
    assert isinstance(trigger, dict)
    assert "pull_request" in trigger
    assert "schedule" in trigger
    self_scan = document["jobs"]["self-scan"]
    assert self_scan["if"] == "github.event_name != 'pull_request'"
    assert self_scan["permissions"] == {
        "contents": "read",
        "security-events": "write",
    }
    steps = self_scan["steps"]
    assert steps[0]["uses"].startswith("actions/checkout@")
    assert steps[1]["uses"] == "./"
    upload = steps[2]
    assert upload["uses"].startswith("github/codeql-action/upload-sarif@")
    assert upload["if"] == "always()"
