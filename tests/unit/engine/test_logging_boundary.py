"""RED contracts for the central leak-safe structlog boundary."""

from __future__ import annotations

import ast
import importlib
import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from structlog.testing import capture_logs

from panopticon.util.leak_check import LeakContext

ROOT = Path(__file__).resolve().parents[3]
ALLOWED_EVENTS = {
    "engine.complete",
    "engine.partial",
    "engine.incomplete",
    "engine.failed",
    "engine.unsupported",
}
FORBIDDEN_LOG_FIELDS = {
    "detail",
    "exception",
    "home",
    "path",
    "secret",
    "token",
    "value",
}


@dataclass(frozen=True, slots=True)
class ExpectedLogRecord:
    """Typed input expected by the logging boundary."""

    event: str
    classification: str
    code: str
    detail: str
    exception: BaseException | None = None


def _logging_contract() -> tuple[
    type[ExpectedLogRecord], Callable[[ExpectedLogRecord, LeakContext], None]
]:
    """Load the logger seam without turning its absence into test collection failure."""
    try:
        spec = importlib.util.find_spec("panopticon.logging")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "central logging boundary is missing"
    module = importlib.import_module("panopticon.logging")
    record_type: type[ExpectedLogRecord] | None = getattr(module, "LogRecord", None)
    emit: Callable[[ExpectedLogRecord, LeakContext], None] | None = getattr(module, "emit", None)
    assert record_type is not None, "typed LogRecord is missing"
    assert emit is not None and callable(emit), "leak-safe emit seam is missing"
    return record_type, emit


def _event_literals(source: str) -> frozenset[str]:
    """Extract stable event names from logger source literals."""
    tree = ast.parse(source)
    return frozenset(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("engine.")
    )


def test_logging_boundary_has_deterministic_event_names_and_structlog() -> None:
    # Given: the central logger source.
    path = ROOT / "src" / "panopticon" / "logging.py"
    assert path.is_file(), "central logging module is missing"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    # Then: event names are closed and consumer configuration remains authoritative.
    assert "structlog" in source
    assert _event_literals(source) == frozenset(ALLOWED_EVENTS)
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "configure"
        for node in ast.walk(tree)
    )
    assert "PrintLoggerFactory" not in source
    assert "sys.stderr" not in source


def test_clean_log_record_emits_only_allowed_machine_fields() -> None:
    # Given: a non-sensitive typed engine transition.
    record_type, emit = _logging_contract()
    record = record_type(
        event="engine.complete",
        classification="COMPLETE",
        code="STAGE_COMPLETE",
        detail="diagnostic",
    )

    # When: the record crosses the central logger.
    with capture_logs() as entries:
        emit(record, LeakContext())

    # Then: only machine classifications cross the log boundary.
    assert entries
    for entry in entries:
        assert not FORBIDDEN_LOG_FIELDS.intersection(entry)
        assert entry.get("event") in ALLOWED_EVENTS
        assert entry.get("classification") == "COMPLETE"
        assert entry.get("code") == "STAGE_COMPLETE"


def test_registered_secret_in_machine_fields_uses_a_safe_fallback() -> None:
    # Given: a registered secret placed in an uppercase machine field.
    record_type, emit = _logging_contract()
    secret = "REGISTERED_SECRET_VALUE"
    record = record_type(
        event="engine.complete",
        classification=secret,
        code="STAGE_COMPLETE",
        detail="ordinary detail",
    )

    # When: the machine fields cross the logging boundary.
    with capture_logs() as entries:
        emit(record, LeakContext(secrets=(secret,)))

    # Then: the value is absent and the event is replaced by stable redaction fields.
    serialized = repr(entries)
    assert entries
    assert secret not in serialized
    assert entries[0].get("event") == "engine.failed"
    assert entries[0].get("classification") == "FAILED"
    assert entries[0].get("code") == "LEAK_REDACTED"


def test_real_home_token_and_exception_values_are_rejected_before_logging() -> None:
    # Given: a diagnostic containing registered sensitive values and an exception message.
    record_type, emit = _logging_contract()
    token = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
    home = "/Users/real-user/.config/panopticon"
    record = record_type(
        event="engine.failed",
        classification="FAILED",
        code="STAGE_ERROR",
        detail=f"token={token} home={home}",
        exception=RuntimeError(token),
    )

    # When: the typed context protects the logger boundary.
    with capture_logs() as entries:
        emit(record, LeakContext(home_paths=(home,), secrets=(token,)))

    # Then: neither matched values nor exception text reaches any captured field.
    serialized = repr(entries)
    assert token not in serialized
    assert home not in serialized
    assert "STAGE_ERROR" in serialized


def test_logging_source_has_no_file_sink_or_raw_persistence_call() -> None:
    # Given: the logger source.
    path = ROOT / "src" / "panopticon" / "logging.py"
    assert path.is_file(), "central logging module is missing"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    # Then: logging stays on the configured stream and does not create artifacts.
    forbidden_names = {"FileHandler", "RotatingFileHandler", "open", "write_text", "write_bytes"}
    assert not any(
        isinstance(node, ast.Name) and node.id in forbidden_names for node in ast.walk(tree)
    )
