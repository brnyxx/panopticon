"""RED contracts for typed engine results, coverage, and plan boundaries."""

from __future__ import annotations

import ast
import importlib
import importlib.util
from pathlib import Path

import pytest

from panopticon.models import Coverage, StageStatus

ROOT = Path(__file__).resolve().parents[3]
ENGINE_MODULES = ("doctor", "watch", "diff", "scan")
EXPECTED_RESULT_STATES = (
    "COMPLETE",
    "PARTIAL",
    "INCOMPLETE",
    "FAILED",
    "UNSUPPORTED",
)
EXPECTED_REASON_CODES = (
    "COMPLETED",
    "VERSION_SELECTED",
    "PARTIAL_COVERAGE",
    "LEGACY_FALLBACK",
    "BUFFER_OVERFLOW",
    "TIMEOUT",
    "DISCOVERY_FAILED",
    "STAGE_ERROR",
    "PROTOCOL_ERROR",
    "TRANSPORT_ERROR",
    "RUNTIME_UNAVAILABLE",
    "UNSUPPORTED_PLATFORM",
    "UNSUPPORTED_TRANSPORT",
    "VERSION_UNSUPPORTED",
    "OFFLINE",
)
EXPECTED_COVERAGE = ("file", "net", "process", "dns", "proxy", "snapshot", "stdio")


def _module_source(module_name: str) -> tuple[Path, str, ast.Module]:
    """Read one future engine contract without failing test collection."""
    qualified = f"panopticon.engine.{module_name}"
    try:
        spec = importlib.util.find_spec(qualified)
    except ModuleNotFoundError:
        spec = None
    assert spec is not None and spec.origin is not None, f"missing engine module: {qualified}"
    path = Path(spec.origin)
    source = path.read_text(encoding="utf-8")
    return path, source, ast.parse(source, filename=str(path))


def _class_definition(tree: ast.Module, name: str) -> ast.ClassDef:
    """Return one named class from a parsed module."""
    matches = tuple(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name
    )
    assert len(matches) == 1, f"missing unique class {name}"
    return matches[0]


def _enum_members(class_definition: ast.ClassDef) -> tuple[str, ...]:
    """Collect simple enum assignment names in source order."""
    names: list[str] = []
    for node in class_definition.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                names.append(target.id)
    return tuple(names)


def _annotation_texts(tree: ast.Module) -> tuple[str, ...]:
    """Collect public boundary annotations for the raw-type audit."""
    annotations: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and not node.target.id.startswith("_")
        ):
            annotations.append(ast.unparse(node.annotation))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            annotations.extend(
                ast.unparse(annotation)
                for annotation in (
                    argument.annotation
                    for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
                )
                if annotation is not None
            )
            if node.returns is not None:
                annotations.append(ast.unparse(node.returns))
    return tuple(annotations)


def test_engine_result_contract_has_exhaustive_typed_states() -> None:
    # Given: the future shared engine contract module.
    _, source, tree = _module_source("contracts")
    status = _class_definition(tree, "EngineStatus")

    # When / Then: the result state is exactly the five boundary outcomes, with no domain string.
    assert _enum_members(status) == EXPECTED_RESULT_STATES
    assert "SKIPPED_DESTRUCTIVE" not in source
    assert all(reason in source for reason in EXPECTED_REASON_CODES)
    diagnostic = _class_definition(tree, "EngineDiagnostic")
    diagnostic_fields = {
        node.target.id
        for node in diagnostic.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert {"code", "detail"} <= diagnostic_fields
    for variant in (
        "CompleteResult",
        "PartialResult",
        "IncompleteResult",
        "FailedResult",
        "UnsupportedResult",
    ):
        variant_definition = _class_definition(tree, variant)
        names = {
            node.target.id
            for node in variant_definition.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        assert {"status", "reason_code", "coverage", "diagnostics"} <= names
        status_annotation = next(
            ast.unparse(node.annotation)
            for node in variant_definition.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "status"
        )
        assert "EngineStatus" in status_annotation
        assert "str" not in status_annotation
    assert "Result: TypeAlias" in source
    assert "frozen=True" in source


def test_engine_reuses_task3_coverage_and_default_is_honestly_not_requested() -> None:
    # Given: the engine contract source and the existing Task3 persistence model.
    _, source, tree = _module_source("contracts")
    module = importlib.import_module("panopticon.engine.contracts")
    duplicate_classes = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name in {"Coverage", "CoverageStatus"}
    }

    # Then: Task3 owns coverage/state, while engine outcomes retain their five-state distinction.
    assert duplicate_classes == set()
    assert "StageStatus" in source
    assert "complete_coverage" not in source
    assert module.Coverage is Coverage
    assert module.StageStatus is StageStatus
    assert Coverage.model_config["frozen"] is True
    coverage = module.CompleteResult().coverage
    assert isinstance(coverage, Coverage)
    assert {getattr(coverage, dimension).status for dimension in EXPECTED_COVERAGE} == {
        StageStatus.NOT_REQUESTED
    }


def test_engine_boundary_uses_no_raw_dict_or_untyped_escape_hatches() -> None:
    # Given: annotations from the shared engine boundary.
    _, _, tree = _module_source("contracts")
    annotations = _annotation_texts(tree)

    # Then: public contracts preserve structured types instead of erasing their shape.
    for annotation in annotations:
        assert "dict" not in annotation.casefold()
        assert "typing.Any" not in annotation
        assert annotation not in {"Any", "object"}


def test_stage_coverage_keeps_all_explicit_dimensions_and_states() -> None:
    # Given: the existing typed coverage model and stage enum.
    coverage_fields = tuple(Coverage.model_fields)
    stage_values = {status.value for status in StageStatus}

    # Then: engine results can express every coverage dimension without a bare stage string.
    assert coverage_fields == EXPECTED_COVERAGE
    assert stage_values == {
        "COMPLETE",
        "PARTIAL",
        "INCOMPLETE",
        "FAILED",
        "UNSUPPORTED",
        "SKIPPED",
        "NOT_REQUESTED",
    }


@pytest.mark.parametrize(
    ("module_name", "protocol_name"),
    (("doctor", "DoctorPlan"), ("watch", "WatchPlan"), ("diff", "DiffPlan"), ("scan", "ScanPlan")),
)
def test_each_engine_pipeline_is_a_protocol_boundary(module_name: str, protocol_name: str) -> None:
    # Given: one engine pipeline module.
    _, source, tree = _module_source(module_name)
    protocol = _class_definition(tree, protocol_name)
    bases = {ast.unparse(base) for base in protocol.bases}
    methods = {
        node.name
        for node in protocol.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    # Then: the module exposes a typed orchestration seam.
    assert "Protocol" in bases
    assert "run" in methods
    assert any(
        any(name in ast.unparse(node.returns) for name in ("Result", "Outcome"))
        for node in protocol.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None
    )
    assert "panopticon.cli" not in source
    assert "panopticon.reporters" not in source


def test_engine_modules_do_not_depend_on_cli_or_reporters() -> None:
    # Given: all four pipeline source files.
    sources = tuple(_module_source(module_name)[1] for module_name in ENGINE_MODULES)

    # Then: dependency direction remains cli/reporters -> engine -> feature packages.
    forbidden = ("panopticon.cli", "panopticon.reporters")
    for source in sources:
        assert not any(forbidden_name in source for forbidden_name in forbidden)
