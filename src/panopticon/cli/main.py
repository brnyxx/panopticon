"""`pano` entry point.

Every subcommand is a thin wrapper: parse flags → call a service in another package → hand the
result to a reporter. Commands raise a clear "delivered by epic Exx" exit until implemented.
"""

from __future__ import annotations

import typer

from panopticon import SCHEMA_VERSION, __version__

app = typer.Typer(
    name="pano",
    help="Panopticon — we don't watch you, we watch your MCPs.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

NOT_IMPLEMENTED_EXIT = 64


def _not_implemented(cmd: str, epic: str) -> int:
    typer.secho(
        f"`pano {cmd}` is not implemented yet — delivered by epic {epic} (see panopticon-buildplan.md).",
        err=True,
        fg=typer.colors.YELLOW,
    )
    return NOT_IMPLEMENTED_EXIT


@app.command()
def version() -> None:
    """Print version and schema version."""
    typer.echo(f"pano {__version__} (schema {SCHEMA_VERSION})")


@app.command()
def doctor(
    client: str | None = typer.Option(None, help="Restrict to one client adapter."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON to stdout."),
    fix: bool = typer.Option(False, help="Run `pano fix` after checks."),
    list_clients: bool = typer.Option(False, "--list-clients", help="Discovery status only."),
) -> None:
    """Discover installed MCPs, check configs, report changes since last look. (E02-E04, E12)"""
    raise typer.Exit(_not_implemented("doctor", "E02"))


@app.command()
def watch(
    target: str = typer.Argument(..., help="Server name, --all, or --self."),
    calls: int = typer.Option(1, help="Calls per tool."),
    timeout: int = typer.Option(20, help="Per-call timeout in seconds."),
    json_out: bool = typer.Option(False, "--json"),
    png: bool = typer.Option(False, help="Render a shareable PNG card."),
) -> None:
    """Run an MCP in the decoy sandbox and record what it does per tool call. (E05-E10, E12)"""
    raise typer.Exit(_not_implemented("watch", "E05"))


@app.command()
def wrap(command: list[str] = typer.Argument(..., help="-- <command...>")) -> None:
    """Transparent stdio relay that records tool-level network events. (E15)"""
    raise typer.Exit(_not_implemented("wrap", "E15"))


@app.command()
def install(client: str, only: str | None = typer.Option(None)) -> None:
    """Inject `pano wrap` into a client's stdio servers (dry-run, backup, undo). (E15)"""
    raise typer.Exit(_not_implemented("install", "E15"))


@app.command()
def uninstall(client: str) -> None:
    """Restore original commands replaced by `pano install`. (E15)"""
    raise typer.Exit(_not_implemented("uninstall", "E15"))


@app.command()
def fix(
    server: str | None = typer.Argument(None),
    rule: str | None = typer.Option(None),
    yes: bool = typer.Option(False, "--yes"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    undo: str | None = typer.Option(None, help="Journal id to undo."),
) -> None:
    """Apply FIX-* remediations: diff, confirm, backup, apply, re-check. (E13)"""
    raise typer.Exit(_not_implemented("fix", "E13"))


@app.command()
def diff(server: str | None = typer.Argument(None), since: str = typer.Option("auto")) -> None:
    """Compare current state against a baseline. (E14)"""
    raise typer.Exit(_not_implemented("diff", "E14"))


@app.command()
def baseline(action: str = typer.Argument(..., help="create|list|show|rm")) -> None:
    """Manage baselines. (E14)"""
    raise typer.Exit(_not_implemented("baseline", "E14"))


@app.command()
def explain(rule_id: str, lang: str = typer.Option("ko", help="ko|en")) -> None:
    """Explain a rule: problem, impact, evidence, action, verification, limits. (E18)"""
    raise typer.Exit(_not_implemented("explain", "E18"))


@app.command()
def scan(
    path: str = typer.Argument("."),
    mode: str = typer.Option("quick", help="quick|standard|deep"),
    sarif: bool = typer.Option(False),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Static / semantic / dynamic analysis of an MCP source tree (upstream line). (E16)"""
    raise typer.Exit(_not_implemented("scan", "E16"))


@app.command()
def ci(
    path: str = typer.Argument("."),
    mode: str = typer.Option("standard", help="quick|standard|deep"),
    sarif: str = typer.Option("pano.sarif"),
    fail_on: str = typer.Option("high", "--fail-on", help="high|medium|incomplete|never"),
    config: str = typer.Option("panopticon.toml"),
) -> None:
    """GitHub Action entry point: scan + SARIF + exit policy (action.yml). (E16)"""
    raise typer.Exit(_not_implemented("ci", "E16"))


@app.command()
def badge() -> None:
    """Generate an SVG 'declared = observed' badge for an MCP repository. (E17)"""
    raise typer.Exit(_not_implemented("badge", "E17"))


if __name__ == "__main__":  # pragma: no cover
    app()
