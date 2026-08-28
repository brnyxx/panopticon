"""Quick and standard deterministic scan orchestration."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from panopticon.analyzers.dependency.scan import (
    AdvisoryPort,
    AdvisoryStatus,
    DependencyFinding,
    run_dependency_scan,
)
from panopticon.analyzers.static.engine import run_static_scan
from panopticon.analyzers.static.findings import StaticFindingView, finding_views
from panopticon.analyzers.static.model import ScannerConfig, StaticConfiguration
from panopticon.engine.contracts import (
    CompleteResult,
    EngineDiagnostic,
    EngineReason,
    EngineStatus,
    IncompleteResult,
    Result,
)
from panopticon.engine.exit_codes import ExitInputs, resolve_exit_code

_AST_RULES = ("SENT-001", "SENT-003", "SENT-004", "SENT-006", "SENT-007")


class ScanMode(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"


class SemgrepPort(Protocol):
    def scan(self, root: Path) -> tuple[StaticFindingView, ...]: ...


@dataclass(frozen=True, slots=True)
class ScanConfig:
    mode: ScanMode
    scanner: ScannerConfig


@dataclass(frozen=True, slots=True)
class ScanRequest:
    path: Path = Path()
    mode: ScanMode | None = None
    semgrep: SemgrepPort | None = None
    advisory: AdvisoryPort | None = None
    offline: bool = False
    cache_available: bool = True


@dataclass(frozen=True, slots=True)
class ScanFinding:
    rule_id: str
    title: str
    severity: str
    fingerprint: str
    path: str | None = None
    line: int | None = None
    column: int | None = None
    kind: str = "confirmed"


@dataclass(frozen=True, slots=True)
class ScanOutcome:
    result: Result
    findings: tuple[ScanFinding, ...]
    mode: ScanMode
    exit_code: int

    @property
    def status(self) -> EngineStatus:
        return self.result.status


class ScanPlan(Protocol):
    def run(self, request: ScanRequest) -> ScanOutcome: ...


def discover_config(root: Path) -> ScanConfig:
    path = root / "panopticon.toml"
    if not path.is_file():
        return ScanConfig(ScanMode.QUICK, ScannerConfig(selected_rule_ids=_AST_RULES))
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError("SCAN_CONFIG_INVALID") from error
    scan = document.get("scan", {})
    if not isinstance(scan, dict):
        raise ValueError("SCAN_CONFIG_INVALID")
    try:
        mode = ScanMode(str(scan.get("mode", ScanMode.QUICK.value)))
    except ValueError as error:
        raise ValueError("SCAN_CONFIG_INVALID") from error
    excludes = scan.get("exclude", [])
    if not isinstance(excludes, list) or not all(isinstance(item, str) for item in excludes):
        raise ValueError("SCAN_CONFIG_INVALID")
    scanner = ScannerConfig(
        selected_rule_ids=_AST_RULES,
        ignore_paths=tuple(item for item in excludes if isinstance(item, str)),
    )
    return ScanConfig(mode, scanner)


def _static_findings(findings: tuple[StaticFindingView, ...]) -> tuple[ScanFinding, ...]:
    return tuple(
        ScanFinding(
            finding.rule_id,
            finding.title,
            finding.severity,
            finding.fingerprint,
            finding.path,
            finding.line,
            finding.column,
            finding.kind,
        )
        for finding in findings
    )


def _dependency_findings(
    findings: tuple[DependencyFinding, ...],
) -> tuple[ScanFinding, ...]:
    return tuple(
        ScanFinding(
            finding.advisory_id,
            finding.summary,
            finding.severity,
            f"{finding.advisory_id}:{finding.package}",
            kind="confirmed",
        )
        for finding in findings
    )


def _outcome(
    result: Result,
    findings: tuple[ScanFinding, ...],
    mode: ScanMode,
) -> ScanOutcome:
    ordered = tuple(
        sorted(
            findings,
            key=lambda finding: (
                finding.rule_id,
                finding.path or "",
                finding.line or 0,
                finding.column or 0,
                finding.fingerprint,
            ),
        )
    )
    exit_code = resolve_exit_code(
        ExitInputs(
            policy_finding=bool(ordered),
            incomplete_required_coverage=result.status
            in {EngineStatus.INCOMPLETE, EngineStatus.UNSUPPORTED},
            runtime_failure=result.status is EngineStatus.FAILED,
        )
    )
    return ScanOutcome(result, ordered, mode, exit_code)


def _incomplete(
    mode: ScanMode,
    findings: tuple[ScanFinding, ...],
    *codes: str,
) -> ScanOutcome:
    result = IncompleteResult(
        reason_code=EngineReason.DISCOVERY_FAILED,
        diagnostics=tuple(
            EngineDiagnostic(code, "required scan dimension incomplete") for code in codes
        ),
    )
    return _outcome(result, findings, mode)


def run_scan(request: ScanRequest) -> ScanOutcome:
    root = request.path.expanduser().resolve()
    if not root.is_dir() or root.is_symlink():
        return _incomplete(ScanMode.QUICK, (), "SCAN_ROOT_INVALID")
    try:
        config = discover_config(root)
        mode = request.mode or config.mode
        static = run_static_scan(StaticConfiguration(root, config.scanner))
    except (OSError, SyntaxError, TimeoutError, ValueError):
        return _incomplete(request.mode or ScanMode.QUICK, (), "STATIC_SCAN_INCOMPLETE")
    findings = _static_findings(finding_views(static.matches))
    if mode is ScanMode.QUICK:
        return _outcome(CompleteResult(), findings, mode)
    semgrep = request.semgrep
    advisory = request.advisory
    if semgrep is None:
        return _incomplete(mode, findings, "SEMGREP_UNAVAILABLE")
    if advisory is None:
        return _incomplete(mode, findings, "ADVISORY_PROVIDER_UNAVAILABLE")
    if not request.cache_available:
        return _incomplete(mode, findings, "ADVISORY_CACHE_UNAVAILABLE")
    try:
        semgrep_findings = semgrep.scan(root)
        dependencies = run_dependency_scan(
            root,
            advisory,
            offline=request.offline,
            cache_available=request.cache_available,
        )
    except (OSError, RuntimeError, TimeoutError, ValueError):
        return _incomplete(mode, findings, "STANDARD_SCAN_INCOMPLETE")
    findings += _static_findings(semgrep_findings)
    findings += _dependency_findings(dependencies.advisory.findings)
    if dependencies.advisory.status is not AdvisoryStatus.COMPLETE:
        return _incomplete(mode, findings, dependencies.advisory.reason_code)
    return _outcome(CompleteResult(), findings, mode)


__all__ = [
    "ScanConfig",
    "ScanFinding",
    "ScanMode",
    "ScanOutcome",
    "ScanPlan",
    "ScanRequest",
    "SemgrepPort",
    "discover_config",
    "run_scan",
]
