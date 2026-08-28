from __future__ import annotations

from pathlib import Path

from panopticon.analyzers.dependency.model import DependencyReason, DependencyStatus
from panopticon.analyzers.dependency.requirements import (
    collect_dependency_input,
    parse_pyproject,
    parse_requirements,
    validate_install_command,
)


def test_requirement_normalization_is_stable_and_rejects_direct_urls() -> None:
    result = parse_requirements(
        (
            "Requests>=2; python_version >= '3.11'",
            "mcp_server==1.2.3",
            "package @ https://example.test/pkg.whl",
        )
    )

    assert result.status is DependencyStatus.INCOMPLETE
    assert [record.name for record in result.requirements] == ["mcp-server", "requests"]
    assert result.diagnostics == ("DIRECT_URL_PROHIBITED:3",)


def test_pyproject_and_pip_shapes_preserve_unknown_states() -> None:
    parsed = parse_pyproject(b'[project]\ndependencies = ["mcp>=1", "FastMCP==2"]\n')
    accepted = validate_install_command(
        ("python3", "-m", "pip", "install", "--requirement", "requirements.txt")
    )
    rejected = validate_install_command(("pip", "install", "https://example.test/a.whl"))

    assert parsed.status is DependencyStatus.COMPLETE
    assert {record.name for record in parsed.requirements} == {"mcp", "fastmcp"}
    assert accepted.status is DependencyStatus.COMPLETE
    assert rejected.status is DependencyStatus.UNSUPPORTED
    assert rejected.reason_code is DependencyReason.INSTALL_SHAPE_UNSUPPORTED


def test_dependency_source_selection_and_fingerprint_are_deterministic(tmp_path: Path) -> None:
    requirement_file = tmp_path / "requirements.txt"
    requirement_file.write_text("mcp==1.2.3\n", encoding="utf-8")

    first = collect_dependency_input(tmp_path)
    second = collect_dependency_input(tmp_path)

    assert first == second
    assert first.status is DependencyStatus.COMPLETE
    assert first.source_paths == ("requirements.txt",)
    assert first.fingerprint is not None

    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["mcp"]\n',
        encoding="utf-8",
    )
    ambiguous = collect_dependency_input(tmp_path)
    assert ambiguous.status is DependencyStatus.INCOMPLETE
    assert ambiguous.reason_code is DependencyReason.INPUT_AMBIGUOUS
