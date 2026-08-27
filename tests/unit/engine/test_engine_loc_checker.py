"""Focused tests for the bounded foundation source-size checker."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
loc_checker = importlib.import_module("check_engine_loc")

MALICIOUS_COMPRESSED_SOURCE: Final[str] = (
    ";".join(f"value = {number}" for number in range(251)) + "\n"
)
LOC_CASES: Final = (
    (
        "# leading comment\nvalue = 1\n# trailing comment\nvalue = 2\n",
        2,
    ),
    ("value = 1; value = 2; value = 3\n", 3),
    (
        "if True:\n    value = 1\n    for item in (1, 2):\n        value += item\n",
        4,
    ),
)


def _pure_loc_checker() -> Callable[[Path], int]:
    """Load the source-size seam without coupling collection to its implementation."""
    checker: Callable[[Path], int] | None = getattr(loc_checker, "pure_loc", None)
    assert checker is not None and callable(checker), "pure LOC checker is missing"
    return checker


def _checker_main() -> Callable[[], int]:
    """Load the command seam used to verify stable machine output."""
    checker_main: Callable[[], int] | None = getattr(loc_checker, "main", None)
    assert checker_main is not None and callable(checker_main), "LOC checker entry point is missing"
    return checker_main


def _write_source(path: Path, source: str) -> Path:
    """Write one disposable source fixture and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_pure_loc_counts_compressed_statements_as_separate_pure_lines(tmp_path: Path) -> None:
    # Given: a malicious fixture with 251 semicolon-separated statements on one physical line.
    path = _write_source(tmp_path / "compressed.py", MALICIOUS_COMPRESSED_SOURCE)

    # When: the source-size checker computes its bounded metric.
    count = _pure_loc_checker()(path)

    # Then: compressed statements cannot evade the 250-statement ceiling.
    assert count == 251


@pytest.mark.parametrize(("source", "expected"), LOC_CASES)
def test_pure_loc_counts_nested_semicolon_comment_and_control_shapes(
    tmp_path: Path,
    source: str,
    expected: int,
) -> None:
    # Given: one valid source shape with comments, semicolons, or nested control statements.
    path = _write_source(tmp_path / "shape.py", source)

    # When: the source-size checker computes the bounded metric.
    count = _pure_loc_checker()(path)

    # Then: the larger of physical pure lines and AST statements is returned.
    assert count == expected


def test_main_emits_stable_output_for_compressed_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a disposable source root containing the malicious compressed fixture.
    repository = tmp_path / "repository"
    path = _write_source(repository / "src" / "compressed.py", MALICIOUS_COMPRESSED_SOURCE)
    monkeypatch.setattr(loc_checker, "ROOT", repository)
    monkeypatch.setattr(loc_checker, "SOURCE_ROOTS", (path.parent,))

    # When: the real checker entry point scans that source root.
    exit_code = _checker_main()()
    captured = capsys.readouterr()

    # Then: one stable machine finding reports the bounded count and configured ceiling.
    assert exit_code == 1
    assert captured.out == "PURE_LOC_EXCEEDED src/compressed.py:251:250\n"
    assert captured.err == ""


def test_main_reports_value_free_syntax_error_without_executing_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: invalid source that would raise a value-bearing exception if executed.
    repository = tmp_path / "repository"
    path = _write_source(
        repository / "src" / "broken.py",
        'raise RuntimeError("SOURCE_VALUE_MUST_NOT_ESCAPE")\nif :\n',
    )
    monkeypatch.setattr(loc_checker, "ROOT", repository)
    monkeypatch.setattr(loc_checker, "SOURCE_ROOTS", (path.parent,))

    # When: the checker parses the source through its command entry point.
    exit_code = _checker_main()()
    captured = capsys.readouterr()

    # Then: syntax failure is explicit, stable, and contains no source-derived value.
    assert exit_code == 1
    assert captured.out == "PURE_LOC_SYNTAX_ERROR src/broken.py\n"
    assert "SOURCE_VALUE_MUST_NOT_ESCAPE" not in captured.out
    assert captured.err == ""
