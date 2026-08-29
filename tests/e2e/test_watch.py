from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from typer.testing import CliRunner

from panopticon.cli.main import app
from panopticon.engine import foundation as engine
from panopticon.engine.contracts import (
    CompleteResult,
    EngineDiagnostic,
    FailedResult,
)
from panopticon.engine.watch_model import TargetMode, TargetSelection, WatchOptions, WatchRequest
from panopticon.engine.watch_service import WatchServiceOutcome
from panopticon.engine.watch_service_targets import WatchTargetReceipt
from panopticon.engine.watch_stages import WatchDependencies, WatchStages


@dataclass(frozen=True)
class Target:
    name: str
    transport: str = "stdio"
    command: str | None = "server"
    args: tuple[str, ...] = ()
    url: str | None = None
    destructive: bool = False


class Inventory:
    def __init__(self, *targets: Target) -> None:
        self.targets = targets

    def select(self, selection: TargetSelection) -> tuple[Target, ...]:
        if selection.mode is TargetMode.NAME:
            return tuple(t for t in self.targets if t.name == selection.name)
        return self.targets


class Local:
    def __init__(self, payload: object = "evidence") -> None:
        self.payload, self.cleaned, self.calls = payload, 0, 0

    def available(self) -> bool:
        return True

    def run(self, target, *, timeout, read_only, env):
        self.calls += 1
        return type(
            "Run",
            (),
            {
                "status": "COMPLETE",
                "reason": "OK",
                "payload": self.payload,
                "coverage": {"stdio": "COMPLETE"},
                "diagnostics": (),
            },
        )()

    def cleanup(self) -> None:
        self.cleaned += 1


class Remote:
    def __init__(self) -> None:
        self.closed = 0
        self.seen = None

    def observe(self, target, *, calls, timeout, idle, headers):
        self.seen = (target, headers)
        return type(
            "Run",
            (),
            {
                "status": "COMPLETE",
                "reason": "OK",
                "payload": "remote",
                "coverage": {"net": "COMPLETE"},
                "diagnostics": (),
            },
        )()

    def close(self) -> None:
        self.closed += 1


@pytest.mark.docker
def test_clean_stdio_and_remote_watch() -> None:
    local = Local()
    remote = Remote()
    target = Target("local")
    remote_target = Target("remote", "http", None, (), "https://example.test", False)
    deps = WatchDependencies(
        Inventory(target, remote_target),
        local=local,
        remote=remote,
        headers={"Authorization": "safe"},
    )
    request = WatchRequest(
        TargetSelection(TargetMode.ALL), WatchOptions(headers=("Authorization",))
    )
    outcomes = WatchStages(deps).run(request)
    assert [o.reason for o in outcomes] == ["OK", "OK"]
    assert local.cleaned == 1
    assert remote.closed == 1


@pytest.mark.docker
def test_uninstrumentable_local_is_unsupported_without_mount() -> None:
    local = Local()
    target = Target("broken", command=None)
    outcome = WatchStages(WatchDependencies(Inventory(target), local=local)).run(
        WatchRequest(TargetSelection(TargetMode.NAME, "broken"))
    )[0]
    assert outcome.status == "UNSUPPORTED"
    assert outcome.reason == "UNINSTRUMENTABLE_LOCAL_TARGET"
    assert local.calls == 0


@pytest.mark.docker
def test_real_cli_self_watch_persists_observation_and_png(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    fixture = Path(__file__).parents[1] / "fixtures" / "mcp" / "node_server.mjs"
    (project / "server.mjs").write_bytes(fixture.read_bytes())
    (project / "wrapper.mjs").write_text(
        "process.argv.push('clean_file_read'); await import('./server.mjs');\n",
        encoding="utf-8",
    )
    (project / "package.json").write_text(
        '{"name":"watch-fixture","bin":"wrapper.mjs"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(project)

    result = CliRunner().invoke(
        app,
        ["watch", "--self", "--offline", "--runtime", "docker", "--png", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "PARTIAL"
    assert "NOT_IMPLEMENTED" not in result.stderr
    observations = tuple((home / ".panopticon" / "observations").rglob("*.json"))
    cards = tuple((home / ".panopticon" / "cards").glob("*.png"))
    assert len(observations) == len(cards) == 1
    assert "real-environment-value" not in observations[0].read_text(encoding="utf-8")


def test_cli_raw_and_selective_environment_are_forwarded_with_deduplication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[WatchRequest] = []

    def run_watch(request: WatchRequest) -> WatchServiceOutcome:
        captured.append(request)
        return WatchServiceOutcome(CompleteResult())

    monkeypatch.setattr(engine, "run_watch", run_watch)
    result = CliRunner().invoke(
        app,
        [
            "watch",
            "demo",
            "--raw",
            "--real-env",
            " TOKEN ,HOME,TOKEN,, ",
        ],
    )

    assert result.exit_code == 0
    assert captured[0].selection == TargetSelection(TargetMode.NAME, "demo")
    assert captured[0].options.raw is True
    assert captured[0].options.real_env == ("TOKEN", "HOME")
    assert "TOKEN" in result.stderr and "HOME" in result.stderr
    assert "real-environment-value" not in result.stderr


def test_cli_self_command_override_is_forwarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[WatchRequest] = []

    def run_watch(request: WatchRequest) -> WatchServiceOutcome:
        captured.append(request)
        return WatchServiceOutcome(CompleteResult())

    monkeypatch.setattr(engine, "run_watch", run_watch)
    result = CliRunner().invoke(
        app,
        [
            "watch",
            "--self",
            "--command",
            "python3",
            "--command",
            "/self/server.py",
        ],
    )

    assert result.exit_code == 0
    assert captured[0].options.self_command == ("python3", "/self/server.py")


def test_cli_rejects_empty_environment_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "run_watch", lambda request: WatchServiceOutcome(CompleteResult()))
    result = CliRunner().invoke(app, ["watch", "demo", "--real-env", " , "])
    assert result.exit_code != 0
    assert "requires at least one key" in result.stderr


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["watch", "--self", "--real-env", "A"], "cannot be combined"),
        (["watch", "--self", "--real-env-all"], "cannot be combined"),
        (["watch", "demo", "--real-env", "A", "--real-env-all"], "mutually exclusive"),
    ],
)
def test_cli_rejects_environment_selection_conflicts(args: list[str], message: str) -> None:
    result = CliRunner().invoke(app, args)
    assert result.exit_code != 0
    assert message in result.stderr


def test_cli_real_environment_all_warns_without_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[WatchRequest] = []
    monkeypatch.setattr(
        engine,
        "run_watch",
        lambda request: captured.append(request) or WatchServiceOutcome(CompleteResult()),
    )
    result = CliRunner().invoke(app, ["watch", "--all", "--real-env-all"])
    assert result.exit_code == 0
    assert captured[0].options.real_env_all is True
    assert "--real-env-all exposes all declared environment values" in result.stderr
    assert "real-environment-value" not in result.stderr


def test_cli_rejects_invalid_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "run_watch", lambda request: WatchServiceOutcome(CompleteResult()))
    result = CliRunner().invoke(app, ["watch", "demo", "--runtime", "containerd"])
    assert result.exit_code != 0


@pytest.mark.parametrize(
    ("args", "selection"),
    [
        (["watch", "--all"], TargetSelection(TargetMode.ALL)),
        (["watch", "demo"], TargetSelection(TargetMode.NAME, "demo")),
        (["watch", "--self"], TargetSelection(TargetMode.SELF)),
    ],
)
def test_cli_selection_modes(monkeypatch: pytest.MonkeyPatch, args, selection) -> None:
    captured: list[WatchRequest] = []
    monkeypatch.setattr(
        engine,
        "run_watch",
        lambda request: captured.append(request) or WatchServiceOutcome(CompleteResult()),
    )
    assert CliRunner().invoke(app, args).exit_code == 0
    assert captured[0].selection == selection


def test_cli_json_and_target_outcome_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    outcome = WatchServiceOutcome(
        FailedResult(diagnostics=(EngineDiagnostic("TARGET_PARTIAL", "target incomplete"),)),
        targets=(WatchTargetReceipt("demo", "FAILED", "TARGET_PARTIAL"),),
    )
    monkeypatch.setattr(engine, "run_watch", lambda request: outcome)
    result = CliRunner().invoke(app, ["watch", "demo", "--json"])
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "FAILED"
    assert payload["targets"][0]["name"] == "demo"
    assert payload["diagnostics"] == [{"code": "TARGET_PARTIAL", "detail": "target incomplete"}]
