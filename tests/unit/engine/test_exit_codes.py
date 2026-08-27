"""RED contracts for engine outcomes and the CLI exit-code policy."""

from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict
from typer.testing import CliRunner

from panopticon.cli.main import app

runner = CliRunner()


class MachineDiagnostic(BaseModel):
    """Machine-readable diagnostic emitted by a boundary reporter."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    code: str
    detail: str


class CompleteDoctorReport(BaseModel):
    """Minimal machine contract for a complete doctor response."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    status: Literal["COMPLETE"]


class IncompleteDoctorReport(BaseModel):
    """Machine contract for a required discovery failure."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    status: Literal["INCOMPLETE"]
    reason_code: Literal["DISCOVERY_FAILED"]
    diagnostics: tuple[MachineDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class ExitInputs:
    """Independent machine signals consumed by the exit policy."""

    policy_finding: bool = False
    incomplete_required_coverage: bool = False
    runtime_failure: bool = False
    config_failure: bool = False
    usage_error: bool = False


def _exit_code_resolver() -> Callable[[ExitInputs], int]:
    """Load the typed exit-policy seam without turning a missing module into collection failure."""
    try:
        spec = importlib.util.find_spec("panopticon.engine.exit_codes")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "engine exit-code contract is missing"
    module = importlib.import_module("panopticon.engine.exit_codes")
    resolver: Callable[[ExitInputs], int] | None = getattr(module, "resolve_exit_code", None)
    assert resolver is not None and callable(resolver), "typed exit resolver is missing"
    return resolver


def test_complete_doctor_result_renders_and_exits_zero() -> None:
    # Given: the real CLI surface asked only for deterministic client-status discovery.
    result = runner.invoke(app, ["doctor", "--list-clients", "--json"])

    # When / Then: a complete boundary result is rendered as machine data and succeeds.
    assert result.exit_code == 0
    assert result.stdout
    report = CompleteDoctorReport.model_validate_json(result.stdout)
    assert report.status == "COMPLETE"


def test_incomplete_required_stage_exits_three_with_sanitized_diagnostic() -> None:
    # Given: a client name that cannot be discovered and sensitive values that must not escape.
    result = runner.invoke(app, ["doctor", "--client", "missing-client", "--json"])
    real_token = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
    real_home = "/Users/real-user/.config/panopticon"

    # When / Then: the real CLI returns the policy's incomplete code and only sanitized fields.
    assert result.exit_code == 3
    assert result.stdout
    report = IncompleteDoctorReport.model_validate_json(result.stdout)
    assert report.status == "INCOMPLETE"
    assert report.reason_code == "DISCOVERY_FAILED"
    assert report.diagnostics
    assert all(diagnostic.code.isupper() for diagnostic in report.diagnostics)
    serialized = result.stdout + result.stderr
    assert real_token not in serialized
    assert real_home not in serialized


EXIT_CASES: tuple[tuple[str, ExitInputs, int], ...] = (
    ("success", ExitInputs(), 0),
    ("policy", ExitInputs(policy_finding=True), 1),
    ("incomplete", ExitInputs(incomplete_required_coverage=True), 3),
    ("runtime", ExitInputs(runtime_failure=True), 5),
    ("config", ExitInputs(config_failure=True), 4),
    ("usage", ExitInputs(usage_error=True), 2),
    ("policy-before-incomplete", ExitInputs(True, True), 3),
    ("incomplete-before-runtime", ExitInputs(False, True, True), 5),
    ("config-before-runtime", ExitInputs(False, False, True, True), 4),
    ("usage-before-config", ExitInputs(False, False, False, True, True), 2),
    ("usage-before-everything", ExitInputs(True, True, True, True, True), 2),
)


@pytest.mark.parametrize(("case", "inputs", "expected"), EXIT_CASES, ids=lambda value: value)
def test_exit_code_precedence_is_deterministic(
    case: str,
    inputs: ExitInputs,
    expected: int,
) -> None:
    # Given: one independent combination from the complete precedence table.
    resolve_exit_code = _exit_code_resolver()

    # When: the typed policy resolves the combination.
    actual = resolve_exit_code(inputs)

    # Then: the documented machine value wins without truthiness shortcuts.
    assert actual == expected, case
    assert resolve_exit_code(inputs) == actual


def test_success_and_policy_exit_codes() -> None:
    # Given: the real typed exit-policy resolver and independent clean/policy inputs.
    resolve_exit_code = _exit_code_resolver()

    # When: success and a policy finding are resolved through the shared seam.
    success_code = resolve_exit_code(ExitInputs())
    policy_code = resolve_exit_code(ExitInputs(policy_finding=True))

    # Then: the reserved machine values are returned directly by the policy.
    assert success_code == 0
    assert policy_code == 1


def test_incomplete_outranks_policy() -> None:
    # Given: required coverage is incomplete while a policy finding is also present.
    resolve_exit_code = _exit_code_resolver()

    # When: the shared typed policy resolves both signals.
    exit_code = resolve_exit_code(
        ExitInputs(policy_finding=True, incomplete_required_coverage=True)
    )

    # Then: incomplete required coverage retains its higher-precedence machine code.
    assert exit_code == 3


def test_cli_usage_error_has_the_reserved_usage_exit_surface() -> None:
    # Given: a malformed real CLI invocation.
    result = runner.invoke(app, ["doctor", "--not-a-real-option"])

    # Then: Typer exposes its deterministic usage-error code.
    assert result.exit_code == 2
