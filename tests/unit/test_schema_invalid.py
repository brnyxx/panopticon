"""JSON Schema rejects malformed persisted records at the trust boundary."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol, TypeAlias, TypeVar

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
FIXTURES = ROOT / "tests" / "fixtures" / "schemas"
JsonValue: TypeAlias = str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None
FormatValue = TypeVar("FormatValue")


class ValidationIssue(Protocol):
    @property
    def absolute_path(self) -> Sequence[str | int]: ...


class SchemaValidator(Protocol):
    def iter_errors(self, instance: JsonValue) -> Iterable[ValidationIssue]: ...

    def validate(self, instance: JsonValue) -> None: ...


def _is_utc_datetime(value: FormatValue) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.utcoffset() == timedelta(0)


def _validator(name: str) -> SchemaValidator:
    schema = json.loads((SCHEMAS / f"{name}.json").read_text())
    checker = FormatChecker()
    checker.checks("date-time")(_is_utc_datetime)
    return Draft202012Validator(schema, format_checker=checker)


def _fixture(name: str) -> dict[str, JsonValue]:
    value: JsonValue = json.loads((FIXTURES / name).read_text())
    assert isinstance(value, dict)
    return value


def test_skipped_destructive_is_reason_not_stage_status() -> None:
    # Given: an otherwise representative observation using the scaffold's eighth status.
    payload = _fixture("observation.json")
    state = payload["state"]
    assert isinstance(state, dict)
    stages = state["stages"]
    assert isinstance(stages, dict)
    stages["probe"] = "SKIPPED_DESTRUCTIVE"

    # When: the generated observation schema checks the stage.
    errors = list(_validator("observation").iter_errors(payload))

    # Then: the stage field itself rejects the widened status vocabulary.
    assert any(tuple(error.absolute_path) == ("state", "stages", "probe") for error in errors)


def test_skipped_destructive_reason_structure_is_accepted() -> None:
    # Given: SKIPPED is the status and SKIPPED_DESTRUCTIVE is its reason code.
    payload = _fixture("observation.json")

    # When: the generated observation schema validates it.
    errors = list(_validator("observation").iter_errors(payload))

    # Then: the complete typed record is valid.
    assert errors == []


def test_unknown_nested_property_is_rejected() -> None:
    # Given: a valid event with an unowned nested property.
    payload = _fixture("event.json")
    payload["secret_extra"] = "unexpected"

    # When / Then: closed generated objects reject it.
    with pytest.raises(ValidationError):
        _validator("event").validate(payload)


@pytest.mark.parametrize(
    "path",
    [
        "C:/Users/Alice/secret.txt",
        r"C:\Users\Alice\secret.txt",
        r"\\server\share\Users\Alice\secret.txt",
        "//server/share/Users/Alice/secret.txt",
        "/mnt/c/Users/Alice/secret.txt",
        "/MNT/C/uSeRs/Alice/secret.txt",
        "/Users/Alice/secret.txt",
        "/uSeRs/Alice/secret.txt",
        "/home/alice/secret.txt",
        "/HoMe/Alice/secret.txt",
    ],
)
def test_native_home_path_forms_are_rejected_by_schema(path: str) -> None:
    # Given: a generated event-schema input carrying a native or canonical home path.
    payload = _fixture("event.json")
    payload["path"] = path

    # When / Then: active schema validation rejects every form.
    with pytest.raises(ValidationError):
        _validator("event").validate(payload)


@pytest.mark.parametrize(
    "path",
    [
        "..",
        "../secret.txt",
        "decoy/../secret.txt",
        "decoy/..",
        "/../secret.txt",
        r"decoy\project\file.txt",
        r"decoy/project\file.txt",
        r"\server\share\file.txt",
        r"/\server/share/file.txt",
    ],
)
def test_traversal_and_backslash_paths_are_rejected_by_schema(path: str) -> None:
    # Given: a generated event-schema input carrying traversal or a backslash.
    payload = _fixture("event.json")
    payload["path"] = path

    # When / Then: active schema validation matches runtime rejection.
    with pytest.raises(ValidationError):
        _validator("event").validate(payload)


@pytest.mark.parametrize(
    "path",
    [
        ".",
        "..hidden",
        "decoy/..hidden/file.txt",
        "file..txt",
        "~/.ssh/config",
        "decoy/project/file.txt",
        "/etc/hosts",
    ],
)
def test_portable_persisted_paths_are_accepted_by_schema(path: str) -> None:
    # Given: a normalized home-relative, decoy-relative, or non-home system path.
    payload = _fixture("event.json")
    payload["path"] = path

    # When: the generated schema validates the event.
    errors = list(_validator("event").iter_errors(payload))

    # Then: accepted path boundaries remain unchanged.
    assert errors == []


def test_bad_datetime_format_is_rejected() -> None:
    # Given: a syntactically invalid timestamp.
    payload = _fixture("wrap_record.json")
    payload["ts"] = "not-a-date"

    # When / Then: active format checking rejects it.
    with pytest.raises(ValidationError):
        _validator("wrap_record").validate(payload)
