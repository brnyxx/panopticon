"""Typer commands for baseline and source analysis operations."""

from __future__ import annotations

from pathlib import Path

import typer

from panopticon.engine.baseline import BaselineRequest, run_baseline
from panopticon.engine.ci import FailOn, ci_exit_code
from panopticon.engine.diff import DiffRequest, run_diff
from panopticon.engine.explain import explain_rule
from panopticon.engine.scan import ScanMode, ScanRequest, run_scan
from panopticon.reporters.baseline import render as render_baseline
from panopticon.reporters.diff import render as render_diff
from panopticon.reporters.explain import render as render_explain
from panopticon.reporters.scan import persist as persist_scan
from panopticon.reporters.scan import persist_succeeded
from panopticon.reporters.scan import render_cli as render_scan


def diff(
    server: str | None = typer.Argument(None),
    since: str = typer.Option("auto"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Compare the current state with a saved baseline."""
    rendered = render_diff(
        run_diff(DiffRequest(server=server, since=since)),
        json_output=json_out,
    )
    typer.echo(rendered.stdout, nl=False)
    typer.echo(rendered.stderr, err=True, nl=False)
    raise typer.Exit(rendered.exit_code)


def baseline(
    action: str = typer.Argument(..., help="create|list|show|rm"),
    identifier: str | None = typer.Argument(None, help="Baseline id for show or rm."),
    label: str | None = typer.Option(None, help="Label for create."),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Create, list, show, or remove saved baselines."""
    rendered = render_baseline(
        run_baseline(BaselineRequest(action, identifier, label)),
        json_output=json_out,
    )
    typer.echo(rendered.stdout, nl=False)
    typer.echo(rendered.stderr, err=True, nl=False)
    raise typer.Exit(rendered.exit_code)


def explain(
    rule_id: str,
    lang: str | None = typer.Option(None, help="ko|en"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Explain a rule's evidence, impact, recommended action, and limits."""
    rendered = render_explain(explain_rule(rule_id, locale=lang), json_output=json_out)
    typer.echo(rendered.stdout, nl=False)
    typer.echo(rendered.stderr, err=True, nl=False)
    raise typer.Exit(rendered.exit_code)


def scan(
    path: str = typer.Argument("."),
    mode: str = typer.Option("quick", help="quick|standard|deep"),
    sarif: bool = typer.Option(False),
    json_out: bool = typer.Option(False, "--json"),
    offline: bool = typer.Option(False, "--offline"),
) -> None:
    """Analyze an MCP source tree and report findings."""
    try:
        selected_mode = ScanMode(mode)
    except ValueError:
        raise typer.BadParameter("mode must be quick or standard") from None
    rendered = render_scan(
        run_scan(ScanRequest(path=Path(path), mode=selected_mode, offline=offline)),
        sarif=sarif or json_out,
    )
    typer.echo(rendered.stdout, nl=False)
    typer.echo(rendered.stderr, err=True, nl=False)
    raise typer.Exit(rendered.exit_code)


def ci(
    path: str = typer.Argument("."),
    mode: str = typer.Option("standard", help="quick|standard|deep"),
    sarif: str = typer.Option("pano.sarif"),
    fail_on: str = typer.Option("high", "--fail-on", help="high|medium|incomplete|never"),
    config: str = typer.Option("panopticon.toml"),
) -> None:
    """Scan a source tree, write SARIF results, and set an exit status."""
    try:
        selected_mode = ScanMode(mode)
        selected_policy = FailOn(fail_on)
    except ValueError:
        raise typer.BadParameter("invalid mode or fail-on policy") from None
    root = Path(path)
    outcome = run_scan(ScanRequest(path=root, mode=selected_mode, config_path=Path(config)))
    target = Path(sarif)
    saved = persist_succeeded(persist_scan(outcome, target))
    rendered = render_scan(outcome)
    typer.echo(rendered.stdout, nl=False)
    typer.echo(rendered.stderr, err=True, nl=False)
    if saved:
        typer.echo(str(target))
    raise typer.Exit(ci_exit_code(outcome, selected_policy, sarif_persisted=saved))


def register(app: typer.Typer) -> None:
    """Register analysis commands on the main CLI application."""
    app.command()(diff)
    app.command()(baseline)
    app.command()(explain)
    app.command()(scan)
    app.command()(ci)
