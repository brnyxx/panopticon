from dataclasses import dataclass

import pytest

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
