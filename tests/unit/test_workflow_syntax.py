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


def test_release_workflow_builds_once_before_guarded_promotion() -> None:
    # Given: the release workflow parsed without YAML 1.1 coercion of the on key
    document = yaml.load(
        (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert isinstance(document, dict)
    assert document["env"]["PYTHONPATH"] == "src"
    trigger = document["on"]
    assert isinstance(trigger, dict)
    dispatch = trigger["workflow_dispatch"]
    assert isinstance(dispatch, dict)
    assert set(trigger) == {"workflow_dispatch"}
    assert dispatch["inputs"]["channel"]["options"] == [
        "build",
        "rehearsal",
        "production",
        "recovery",
    ]
    jobs = document["jobs"]
    assert isinstance(jobs, dict)
    assert {
        "release-context",
        "quality",
        "python-package",
        "binary",
        "npm-package",
        "assemble",
        "draft",
        "verify-images",
        "testpypi",
        "promotion-verify",
        "pypi",
        "npm",
        "promotion-images",
        "publish-github",
    } == set(jobs)
    assert jobs["testpypi"]["environment"] == "testpypi"
    assert jobs["pypi"]["environment"] == "pypi"
    assert jobs["npm"]["environment"] == "npm"
    assert jobs["npm"]["permissions"]["id-token"] == "write"
    assert jobs["promotion-images"]["permissions"] == {"packages": "read"}
    assert any(
        str(step.get("uses", "")).startswith("docker/login-action@")
        for step in jobs["promotion-images"]["steps"]
    )
    assert jobs["publish-github"]["environment"] == "release"
    assert set(jobs["publish-github"]["needs"]) == {"pypi", "npm", "release-context"}
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "TODO" not in text
    assert "1.0.0" not in text
    assert "v1.0.0" not in text
    assert "scripts/release_context.py" in text
    assert "inputs.version" not in text
    assert jobs["draft"]["if"] == "inputs.channel == 'rehearsal'"
    assert set(jobs["draft"]["needs"]) == {
        "assemble",
        "testpypi",
        "verify-images",
        "release-context",
    }
    assert jobs["testpypi"]["if"] == "inputs.channel == 'rehearsal'"
    assert set(jobs["testpypi"]["needs"]) == {"assemble", "release-context"}
    assert "--clobber" not in str(jobs["draft"])
    testpypi_publish = next(
        step
        for step in jobs["testpypi"]["steps"]
        if str(step.get("uses", "")).startswith("pypa/gh-action-pypi-publish@")
    )
    assert testpypi_publish["if"] == "steps.testpypi-state.outputs.publish == 'true'"
    assert testpypi_publish["with"]["packages-dir"] == "publish-dist"
    assert "verify_index" in str(jobs["testpypi"])
    assert "test-files.pythonhosted.org" in str(jobs["testpypi"])
    assert 'uvx --from "$wheel_url" pano version' in str(jobs["testpypi"])
    assert "pano $PANO_VERSION (schema 1.0)" in str(jobs["testpypi"])
    for job in jobs.values():
        for step in job.get("steps", []):
            if "uses" in step:
                assert len(step["uses"].rsplit("@", 1)[1]) == 40


def test_recovery_path_is_append_only_and_reuses_retained_artifacts() -> None:
    document = yaml.load(
        (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    dispatch = document["on"]["workflow_dispatch"]
    assert dispatch["inputs"]["source_run_id"]["required"] == "false"
    assert dispatch["inputs"]["source_sha"]["required"] == "false"
    jobs = document["jobs"]
    assert jobs["quality"]["if"] == "inputs.channel == 'build' || inputs.channel == 'rehearsal'"
    assert jobs["promotion-verify"]["if"] == (
        "inputs.channel == 'production' || inputs.channel == 'recovery'"
    )
    assert jobs["promotion-verify"]["permissions"] == {
        "actions": "read",
        "contents": "write",
    }
    assert jobs["pypi"]["environment"] == "pypi"
    assert jobs["npm"]["environment"] == "npm"
    assert jobs["publish-github"]["environment"] == "release"
    publish = next(
        step
        for step in jobs["pypi"]["steps"]
        if str(step.get("uses", "")).startswith("pypa/gh-action-pypi-publish@")
    )
    assert publish["if"] == "steps.pypi-state.outputs.publish == 'true'"
    assert publish["with"]["packages-dir"] == "publish-dist"
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "recovery-bundle" in text
    assert "/jobs?per_page=100" in str(jobs["promotion-verify"])
    assert "verify_run_jobs" in str(jobs["publish-github"])
    forbidden = ("uv build", "pyinstaller", "assemble_release.py", "release upload", "--clobber")
    for name in (
        "promotion-verify",
        "pypi",
        "promotion-images",
        "npm",
        "publish-github",
    ):
        assert not any(item in str(jobs[name]) for item in forbidden)
        for step in jobs[name]["steps"]:
            if "uses" in step:
                assert len(step["uses"].rsplit("@", 1)[1]) == 40
    downloads = [
        step
        for name in ("promotion-verify", "pypi", "npm", "publish-github")
        for step in jobs[name]["steps"]
        if str(step.get("uses", "")).startswith("actions/download-artifact@")
    ]
    assert downloads
    assert all(step["with"]["github-token"] == "${{ github.token }}" for step in downloads)


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


def test_platform_matrix_is_exact_and_uses_immutable_actions() -> None:
    document = yaml.load(
        (ROOT / ".github" / "workflows" / "platform.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    jobs = document["jobs"]
    include = jobs["probe"]["strategy"]["matrix"]["include"]
    labels = {entry["label"] for entry in include}
    assert labels == {
        "darwin-arm64",
        "darwin-x86_64",
        "linux-amd64",
        "linux-arm64",
        "windows-x64",
    }
    runs = {entry["label"]: entry["runs-on"] for entry in include}
    assert runs["windows-x64"] == "windows-2025"
    assert jobs["probe-wsl2"]["runs-on"] == "windows-2025"
    assert "run_wsl2_probe.ps1" in jobs["probe-wsl2"]["steps"][1]["run"]
    assert set(jobs["validate"]["needs"]) == {"probe", "probe-wsl2"}
    for job in jobs.values():
        for step in job.get("steps", []):
            if "uses" in step:
                assert "@" in step["uses"]
                assert len(step["uses"].rsplit("@", 1)[1]) == 40
