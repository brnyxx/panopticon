"""Typer command for running MCP watch observations."""

from __future__ import annotations

import typer

from panopticon.engine import foundation as engine
from panopticon.reporters import watch as watch_reporter


def register(app: typer.Typer) -> None:
    """Register the watch command on the main application."""

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
        raw: bool = typer.Option(
            False, "--raw", help="Retain raw tracer events for this run only."
        ),
        command: list[str] | None = typer.Option(
            None,
            "--command",
            help="Self MCP command argv element; repeat for each element.",
        ),
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
            raise typer.BadParameter("--real-env/--real-env-all cannot be combined with --self")
        if command and not self_target:
            raise typer.BadParameter("--command requires --self")
        if real_keys and real_env_all:
            raise typer.BadParameter("--real-env and --real-env-all are mutually exclusive")
        if real_env_all:
            typer.echo(
                "WARNING: --real-env-all exposes all declared environment values to the target.",
                err=True,
            )
        elif real_keys:
            typer.echo(
                "WARNING: --real-env exposes selected environment values to the target: "
                + ", ".join(real_keys),
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
                        raw=raw,
                        self_command=tuple(command or ()),
                    ),
                )
            ),
            json_output=json_out,
        )
        typer.echo(rendered.stdout, nl=False)
        typer.echo(rendered.stderr, err=True, nl=False)
        raise typer.Exit(rendered.exit_code)
