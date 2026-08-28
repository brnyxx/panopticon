from typer.testing import CliRunner

from panopticon.cli.main import app

runner = CliRunner()


def test_analysis_commands_are_registered() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("diff", "baseline", "explain", "scan", "ci"):
        assert command in result.stdout


def test_scan_rejects_malformed_mode() -> None:
    result = runner.invoke(app, ["scan", "--mode", "malformed"])
    assert result.exit_code == 2
