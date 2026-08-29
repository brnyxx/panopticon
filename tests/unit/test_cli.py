import json
import re

from typer.testing import CliRunner

from panopticon import SCHEMA_VERSION
from panopticon.cli.main import app

runner = CliRunner()


def test_version_prints_schema() -> None:
    r = runner.invoke(app, ["version"])
    assert r.exit_code == 0
    assert SCHEMA_VERSION in r.stdout


def test_help_is_user_facing_and_documents_real_environment_opt_ins() -> None:
    root_help = runner.invoke(app, ["--help"])
    assert root_help.exit_code == 0
    assert not re.search(r"\(E\d{2}[^)]*\)|upstream line", root_help.stdout, re.IGNORECASE)

    watch_help = runner.invoke(app, ["watch", "--help"])
    assert watch_help.exit_code == 0
    assert "selected declared environment values" in watch_help.stdout
    assert "all declared environment values" in watch_help.stdout
    assert "broad exposure" in watch_help.stdout


def test_doctor_without_configs_is_explicitly_incomplete(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["doctor", "--json", "--offline"])
    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason_code"] == "DISCOVERY_FAILED"
