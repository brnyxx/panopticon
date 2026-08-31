import json
import re

from typer.main import get_command
from typer.testing import CliRunner

from panopticon import SCHEMA_VERSION
from panopticon.cli.main import app
from panopticon.i18n.messages import epilog

runner = CliRunner()


def test_version_prints_schema() -> None:
    r = runner.invoke(app, ["version"])
    assert r.exit_code == 0
    assert SCHEMA_VERSION in r.stdout


def test_help_is_user_facing_and_documents_real_environment_opt_ins() -> None:
    root_help = runner.invoke(app, ["--help"], terminal_width=160)
    assert root_help.exit_code == 0
    assert not re.search(r"\(E\d{2}[^)]*\)|upstream line", root_help.stdout, re.IGNORECASE)

    watch_help = runner.invoke(app, ["watch", "--help"], terminal_width=160)
    assert watch_help.exit_code == 0
    watch_command = get_command(app).commands["watch"]
    option_names = {
        option for parameter in watch_command.params for option in getattr(parameter, "opts", ())
    }
    assert {"--real-env", "--real-env-all"} <= option_names
    assert not re.search(r"\(E\d{2}[^)]*\)|upstream line", watch_help.stdout, re.IGNORECASE)
    root_epilog = epilog()
    assert root_epilog.index("pano doctor --offline") < root_epilog.index(
        "pano watch SERVER_NAME --offline"
    )
    assert root_epilog.index("pano watch SERVER_NAME --offline") < root_epilog.index(
        "pano explain RULE_ID --lang ko"
    )
    assert root_epilog.index("pano explain RULE_ID --lang ko") < root_epilog.index(
        "uv tool install panopticon-mcp==1.0.2"
    )


def test_doctor_without_configs_is_explicitly_incomplete(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["doctor", "--json", "--offline"])
    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason_code"] == "DISCOVERY_FAILED"


def test_doctor_korean_terminal_appends_next_command(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["doctor", "--offline", "--locale", "ko"])
    assert result.exit_code == 3
    assert "다음: pano watch SERVER_NAME --offline" in result.stdout


def test_doctor_json_is_identical_across_locales(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    english = runner.invoke(app, ["doctor", "--json", "--offline", "--locale", "en"])
    korean = runner.invoke(app, ["doctor", "--json", "--offline", "--locale", "ko"])
    assert english.exit_code == korean.exit_code
    assert english.stdout == korean.stdout
