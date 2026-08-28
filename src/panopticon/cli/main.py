"""`pano` entry point.

Every subcommand is a thin wrapper: parse flags → call a service in another package → hand the
result to a reporter. Commands raise a clear "delivered by epic Exx" exit until implemented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

import typer

from panopticon import SCHEMA_VERSION, __version__
from panopticon.cli import analysis_commands
from panopticon.engine import foundation as engine
from panopticon.engine.badge import run_badge
from panopticon.engine.exit_codes import NOT_IMPLEMENTED_EXIT
from panopticon.engine.fix import FixCommandRequest, run_fix
from panopticon.engine.install import InstallAction, InstallRequest, run_install, run_uninstall
from panopticon.engine.wrap import WrapRequest, run_wrap
from panopticon.reporters import doctor as doctor_reporter
from panopticon.reporters import watch as watch_reporter
from panopticon.reporters.fix import render as render_fix
from panopticon.reporters.install import render as render_install
from panopticon.reporters.wrap import render as render_wrap

__all__ = ["NOT_IMPLEMENTED_EXIT"]

app = typer.Typer(
    name="pano",
    help="Panopticon — we don't watch you, we watch your MCPs.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _not_implemented(cmd: str, epic: str) -> int:
    typer.secho(
        f"`pano {cmd}` is not implemented yet — delivered by epic {epic} (see buildplan).",
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
    offline: bool = typer.Option(False, "--offline", help="Do not query remote history sources."),
) -> None:
    """Discover installed MCPs, check configs, report changes since last look. (E02-E04, E12)"""
    rendered = doctor_reporter.render(
        engine.doctor_outcome(
            engine.DoctorRequest(client=client, list_clients=list_clients, fix=fix, offline=offline)
        ),
        json_output=json_out,
    )
    typer.echo(rendered.stdout, nl=False)
    typer.echo(rendered.stderr, err=True, nl=False)
    raise typer.Exit(rendered.exit_code)


@app.command()
def watch(
    target: str | None = typer.Argument(None, help="Server name."),
    all_targets: bool = typer.Option(False, "--all"),
    self_target: bool = typer.Option(False, "--self"),
    calls: int = typer.Option(1, help="Calls per tool."),
    timeout: int = typer.Option(20, help="Per-call timeout in seconds."),
    idle: float = typer.Option(0.0, help="Idle observation seconds."),
    arg: list[str] | None = typer.Option(None, "--arg", help="Per-tool JSON override."),
    real_env: str | None = typer.Option(
        None, "--real-env", help="Pass selected environment keys (comma-separated)."
    ),
    real_env_all: bool = typer.Option(
        False, "--real-env-all", help="Pass all declared environment values (unsafe)."
    ),
    header: list[str] | None = typer.Option(None, "--header"),
    allow_destructive: bool = typer.Option(False, "--allow-destructive"),
    offline: bool = typer.Option(False, "--offline"),
    runtime: str | None = typer.Option(None, "--runtime"),
    json_out: bool = typer.Option(False, "--json"),
    png: bool = typer.Option(False, "--png", help="Persist a PNG evidence card."),
) -> None:
    """Run an MCP in the decoy sandbox and record what it does per tool call. (E05-E10, E12)"""
    selected = sum((target is not None, all_targets, self_target))
    if selected != 1:
        raise typer.BadParameter("select one server name, --all, or --self")
    real_keys = tuple(
        dict.fromkeys(key.strip() for key in (real_env or "").split(",") if key.strip())
    )
    if real_env is not None and not real_keys:
        raise typer.BadParameter("--real-env requires at least one key")
    if (real_keys or real_env_all) and self_target:
        raise typer.BadParameter("--real-env cannot be combined with --self")
    if real_keys and real_env_all:
        raise typer.BadParameter("--real-env and --real-env-all are mutually exclusive")
    if real_env_all:
        typer.echo(
            "WARNING: --real-env-all exposes all declared environment values to the target.",
            err=True,
        )
    if runtime not in {None, "docker", "podman"}:
        raise typer.BadParameter("--runtime must be docker or podman")
    mode = (
        engine.TargetMode.ALL
        if all_targets
        else engine.TargetMode.SELF
        if self_target
        else engine.TargetMode.NAME
    )
    name = target if mode is engine.TargetMode.NAME else None
    rendered = watch_reporter.render(
        engine.run_watch(
            engine.WatchRequest(
                engine.TargetSelection(mode, name),
                engine.WatchOptions(
                    calls=calls,
                    timeout=timeout,
                    idle=idle,
                    args=tuple(arg or ()),
                    real_env=real_keys,
                    real_env_all=real_env_all,
                    headers=tuple(header or ()),
                    allow_destructive=allow_destructive,
                    self_read_only=self_target,
                    offline=offline,
                    runtime=runtime,
                    png=png,
                ),
            )
        ),
        json_output=json_out,
    )
    typer.echo(rendered.stdout, nl=False)
    typer.echo(rendered.stderr, err=True, nl=False)
    raise typer.Exit(rendered.exit_code)


@app.command()
def wrap(
    command: list[str] = typer.Argument(..., help="-- <command...>"),
    server_id: str | None = typer.Option(None),
    installation_id: str | None = typer.Option(None),
) -> None:
    """Transparent stdio relay that records tool-level network events. (E15)"""
    rendered = render_wrap(
        run_wrap(
            WrapRequest(
                tuple(command),
                server_id=server_id,
                installation_id=installation_id,
            )
        )
    )
    typer.echo(rendered.stderr, err=True, nl=False)
    raise typer.Exit(rendered.exit_code)


@app.command()
def install(
    client: str,
    only: str | None = typer.Option(None),
    config: Path | None = typer.Option(None, "--config"),
    yes: bool = typer.Option(False, "--yes"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    pano_command: str | None = typer.Option(None, "--pano-command"),
) -> None:
    """Inject `pano wrap` into a client's stdio servers (dry-run, backup, undo). (E15)"""
    rendered = render_install(
        run_install(
            InstallRequest(
                client,
                only=only,
                config_path=config,
                dry_run=dry_run or not yes,
                yes=yes,
                pano_command=pano_command,
            )
        )
    )
    typer.echo(rendered.stdout, nl=False)
    typer.echo(rendered.stderr, err=True, nl=False)
    raise typer.Exit(rendered.exit_code)


@app.command()
def uninstall(
    client: str,
    only: str | None = typer.Option(None),
    config: Path | None = typer.Option(None, "--config"),
    yes: bool = typer.Option(False, "--yes"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Restore original commands replaced by `pano install`. (E15)"""
    rendered = render_install(
        run_uninstall(
            InstallRequest(
                client,
                action=InstallAction.UNINSTALL,
                only=only,
                config_path=config,
                dry_run=dry_run or not yes,
                yes=yes,
            )
        )
    )
    typer.echo(rendered.stdout, nl=False)
    typer.echo(rendered.stderr, err=True, nl=False)
    raise typer.Exit(rendered.exit_code)


@app.command()
def fix(
    server: str | None = typer.Argument(None),
    rule: str | None = typer.Option(None),
    yes: bool = typer.Option(False, "--yes"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    undo: str | None = typer.Option(None, help="Journal id to undo."),
    value: str | None = typer.Option(None, help="Selected replacement value or env key."),
    version: str | None = typer.Option(None, help="Exact version selected by the user."),
    client: str | None = typer.Option(None, help="Limit discovery to one client."),
    config: Path | None = typer.Option(None, help="Explicit generic client config path."),
) -> None:
    """Apply FIX-* remediations: diff, confirm, backup, apply, re-check. (E13)"""
    rendered = render_fix(
        run_fix(
            FixCommandRequest(
                server=server,
                rule=rule,
                yes=yes,
                dry_run=dry_run,
                undo=undo,
                value=value,
                version=version,
                client=client,
                config_path=config,
            )
        )
    )
    typer.echo(rendered.stdout, nl=False)
    typer.echo(rendered.stderr, err=True, nl=False)
    raise typer.Exit(rendered.exit_code)


analysis_commands.register(app)


@app.command()
def badge(
    observation: Path = typer.Argument(..., help="Persisted observation JSON."),
    output: Path = typer.Option(..., "--output", help="SVG output path."),
    locale: str = typer.Option("en", "--locale", case_sensitive=False),
) -> None:
    """Generate an accessible evidence badge from a persisted observation. (E17)"""
    if locale not in {"en", "ko"}:
        raise typer.BadParameter("locale must be en or ko", param_hint="--locale")
    locale_value = cast(Literal["en", "ko"], locale)
    result = run_badge(observation, output, locale=locale_value)
    if result.model is None:
        assert result.diagnostic is not None
        typer.echo(result.diagnostic.code, err=True)
        raise typer.Exit(1)
    typer.echo(str(output))


if __name__ == "__main__":  # pragma: no cover
    app()
