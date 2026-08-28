from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from typer.testing import CliRunner

from panopticon.cli.main import app
from panopticon.engine.watch_model import TargetMode, TargetSelection, WatchOptions, WatchRequest
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
