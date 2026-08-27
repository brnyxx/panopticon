"""RED contracts for strict affected CI and Make targets."""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
CI_PATH = ROOT / ".github" / "workflows" / "ci.yml"
MAKE_PATH = ROOT / "Makefile"
REQUIRED_CHECKS = (
    "ruff check",
    "ruff format --check",
    "mypy",
    "pytest",
    "validate_schemas.py",
    "check_i18n.py",
    "check_phrases.py",
    "check_rules.py",
    "check_persistence_boundary.py",
)


def test_ci_workflow_is_parseable() -> None:
    # Given: the checked-in CI workflow.
    document = yaml.load(CI_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    # Then: syntax remains a YAML mapping.
    assert isinstance(document, dict)


def test_ci_has_all_strict_foundation_checks_without_enabling_self_scan() -> None:
    # Given: the workflow text and its parsed machine shape.
    text = CI_PATH.read_text(encoding="utf-8")
    document = yaml.load(text, Loader=yaml.BaseLoader)
    assert isinstance(document, dict)

    # Then: every affected foundation check is present and unfinished self-scan stays disabled.
    for check in REQUIRED_CHECKS:
        assert check in text
    assert "check-no-excuse-rules.py" in text or "check_no_excuse" in text
    assert "250" in text
    assert "self-scan:" in text
    assert "if: false" in text


def test_ci_jobs_keep_docker_and_unfinished_scan_separate() -> None:
    # Given: the workflow source.
    text = CI_PATH.read_text(encoding="utf-8")

    # Then: Docker remains its own job while the unfinished analyze job is not enabled.
    assert "test-docker:" in text
    self_scan_start = text.index("self-scan:")
    self_scan = text[self_scan_start:]
    assert "if: false" in self_scan


async def test_make_ci_dry_run_runs_schema_validator_on_real_surface() -> None:
    # Given: the real repository Makefile and its existing schemas directory.
    process = await asyncio.create_subprocess_exec(
        "make",
        "-n",
        "ci",
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # When: Make expands the CI target without executing commands.
    stdout, _ = await process.communicate()

    # Then: the schema validator recipe is present despite the schemas directory.
    assert process.returncode == 0
    assert stdout is not None
    assert b"uv run python scripts/validate_schemas.py" in stdout


def test_make_ci_composes_the_same_strict_foundation_checks() -> None:
    # Given: the repository's CI target.
    text = MAKE_PATH.read_text(encoding="utf-8")

    # Then: local CI names every strict affected check and the pure-LOC audit.
    for check in REQUIRED_CHECKS:
        assert check.split()[0] in text or check in text
    assert "check-no-excuse-rules.py" in text or "check_no_excuse" in text
    assert "250" in text
    assert "ci:" in text
    assert "test-docker" not in text.split("ci:", maxsplit=1)[1].split("\n\n", maxsplit=1)[0]
