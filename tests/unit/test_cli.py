from typer.testing import CliRunner

from panopticon import SCHEMA_VERSION
from panopticon.cli.main import NOT_IMPLEMENTED_EXIT, app

runner = CliRunner()


def test_version_prints_schema() -> None:
    r = runner.invoke(app, ["version"])
    assert r.exit_code == 0
    assert SCHEMA_VERSION in r.stdout


def test_unimplemented_commands_point_to_epic() -> None:
    r = runner.invoke(app, ["doctor"])
    assert r.exit_code == NOT_IMPLEMENTED_EXIT
