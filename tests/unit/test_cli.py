import json

from typer.testing import CliRunner

from panopticon import SCHEMA_VERSION
from panopticon.cli.main import app

runner = CliRunner()


def test_version_prints_schema() -> None:
    r = runner.invoke(app, ["version"])
    assert r.exit_code == 0
    assert SCHEMA_VERSION in r.stdout


def test_doctor_without_configs_is_explicitly_incomplete(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["doctor", "--json", "--offline"])
    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason_code"] == "DISCOVERY_FAILED"
