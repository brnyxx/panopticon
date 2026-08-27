"""Runtime models reject incomplete or leak-prone persisted records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeAlias

import pytest
from pydantic import ValidationError

from panopticon.models import Event, InstalledServer, Observation

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "schemas"
JsonValue: TypeAlias = str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None


def _fixture(name: str) -> dict[str, JsonValue]:
    value: JsonValue = json.loads((FIXTURES / name).read_text())
    assert isinstance(value, dict)
    return value


def test_real_home_and_missing_stage_reason_are_rejected() -> None:
    # Given: one record leaks an absolute home and another omits a stage reason.
    installed = _fixture("installed_server.json")
    installed["config_path"] = "/Users/alice/.config/client.json"
    observation = _fixture("observation.json")
    state = observation["state"]
    assert isinstance(state, dict)
    stages = state["stages"]
    assert isinstance(stages, dict)
    probe = stages["probe"]
    assert isinstance(probe, dict)
    del probe["reason_code"]

    # When / Then: both untrusted records fail runtime parsing.
    with pytest.raises(ValidationError) as home_error:
        InstalledServer.model_validate_json(json.dumps(installed))
    with pytest.raises(ValidationError) as reason_error:
        Observation.model_validate_json(json.dumps(observation))
    assert home_error.value.errors()[0]["loc"] == ("config_path",)
    assert reason_error.value.errors()[0]["loc"] == (
        "state",
        "stages",
        "probe",
        "SKIPPED",
        "reason_code",
    )


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
def test_native_home_path_forms_are_rejected_by_runtime(path: str) -> None:
    # Given: a real persisted event carrying a native or canonical home path.
    payload = _fixture("event.json")
    payload["path"] = path

    # When / Then: runtime parsing rejects every form with the stable typed reason.
    with pytest.raises(ValidationError) as path_error:
        Event.model_validate_json(json.dumps(payload))
    assert "REAL_HOME_PATH" in str(path_error.value)


@pytest.mark.parametrize(
    ("path", "reason_code"),
    [
        ("..", "PATH_TRAVERSAL"),
        ("../secret.txt", "PATH_TRAVERSAL"),
        ("decoy/../secret.txt", "PATH_TRAVERSAL"),
        ("decoy/..", "PATH_TRAVERSAL"),
        ("/../secret.txt", "PATH_TRAVERSAL"),
        (r"decoy\project\file.txt", "REAL_HOME_PATH"),
        (r"decoy/project\file.txt", "REAL_HOME_PATH"),
        (r"\server\share\file.txt", "REAL_HOME_PATH"),
        (r"/\server/share/file.txt", "REAL_HOME_PATH"),
    ],
)
def test_traversal_and_backslash_paths_are_rejected_by_runtime(path: str, reason_code: str) -> None:
    # Given: a persisted event carrying traversal or a non-normalized separator.
    payload = _fixture("event.json")
    payload["path"] = path

    # When / Then: parent runtime behavior rejects it with the stable typed reason.
    with pytest.raises(ValidationError) as path_error:
        Event.model_validate_json(json.dumps(payload))
    assert reason_code in str(path_error.value)


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
def test_portable_persisted_paths_are_accepted_by_runtime(path: str) -> None:
    # Given: a normalized home-relative, decoy-relative, or non-home system path.
    payload = _fixture("event.json")
    payload["path"] = path

    # When: the event crosses the runtime persistence boundary.
    event = Event.model_validate_json(json.dumps(payload))

    # Then: the accepted path round-trips unchanged.
    parsed: JsonValue = json.loads(event.model_dump_json())
    assert isinstance(parsed, dict)
    assert parsed["path"] == path


def test_models_are_frozen_and_unknown_fields_are_rejected() -> None:
    # Given: a parsed installation and an input with an unknown field.
    payload = (FIXTURES / "installed_server.json").read_text()
    installation = InstalledServer.model_validate_json(payload)
    unknown = _fixture("installed_server.json")
    unknown["unexpected"] = True

    # When / Then: mutation and unknown input are both rejected.
    with pytest.raises(ValidationError):
        installation.__setattr__("name", "changed")
    with pytest.raises(ValidationError) as unknown_error:
        InstalledServer.model_validate_json(json.dumps(unknown))
    assert unknown_error.value.errors()[0]["type"] == "extra_forbidden"
