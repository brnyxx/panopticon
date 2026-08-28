from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from panopticon.engine.watch_local import LocalRun, LocalTarget
from panopticon.engine.watch_model import (
    Evidence,
    PersistenceCandidate,
    TargetMode,
    TargetSelection,
    WatchOptions,
    WatchRequest,
    WatchTarget,
)
from panopticon.engine.watch_remote import RemoteRun, RemoteTarget
from panopticon.engine.watch_stages import WatchDependencies, WatchStages


@dataclass
class Target:
    name: str
    transport: str = "stdio"
    destructive: bool = False
    command: str | None = "tool"
    args: tuple[str, ...] = ()
    url: str | None = None


class Inventory:
    def __init__(self, *targets: WatchTarget) -> None:
        self.targets = targets

    def select(self, selection: TargetSelection) -> tuple[WatchTarget, ...]:
        return self.targets


class Local:
    def __init__(self, available: bool = True, result: LocalRun | None = None) -> None:
        self.ok = available
        self.result = result
        self.cleaned = 0
        self.target: LocalTarget | None = None
        self.options: tuple[float, bool, Mapping[str, str]] | None = None

    def available(self) -> bool:
        return self.ok

    def run(
        self,
        target: LocalTarget,
        *,
        timeout: float,
        read_only: bool,
        env: Mapping[str, str],
    ) -> LocalRun:
        self.target = target
        self.options = (timeout, read_only, env)
        if self.result is None:
            raise RuntimeError("missing fixture result")
        return self.result

    def cleanup(self) -> None:
        self.cleaned += 1


class Remote:
    def __init__(self, result: RemoteRun) -> None:
        self.result = result
        self.closed = 0
        self.target: RemoteTarget | None = None

    def observe(
        self,
        target: RemoteTarget,
        *,
        calls: int,
        timeout: float,
        idle: float,
        headers: Mapping[str, str],
    ) -> RemoteRun:
        self.target = target
        return self.result

    def close(self) -> None:
        self.closed += 1


class Decoy:
    def manifest(self) -> Mapping[str, str]:
        return {"TOKEN": "secret", "OTHER": "x"}

    def archive(self) -> bytes:
        return b"archive"


class Stage:
    def __init__(self, value: PersistenceCandidate) -> None:
        self.value = value
        self.calls = 0

    def collect(self, evidence: Evidence) -> PersistenceCandidate:
        self.calls += 1
        return self.value

    def extract(self, evidence: Evidence) -> PersistenceCandidate:
        self.calls += 1
        return self.value

    def apply(
        self,
        declared: PersistenceCandidate,
        *,
        target: WatchTarget,
    ) -> PersistenceCandidate:
        self.calls += 1
        return self.value

    def evaluate(
        self,
        evidence: Evidence,
        *,
        target: WatchTarget,
    ) -> tuple[PersistenceCandidate, ...]:
        self.calls += 1
        return (self.value,)

    def drive(
        self,
        evidence: Evidence,
        *,
        calls: int,
        args: tuple[str, ...],
        timeout: float,
        idle: float,
    ) -> Evidence:
        self.calls += 1
        return self.value


class Cancel:
    def __init__(self, value: bool = True) -> None:
        self.value = value

    def cancelled(self) -> bool:
        return self.value


def request(
    *,
    real_env: bool = False,
    args: tuple[str, ...] = (),
    headers: tuple[str, ...] = (),
) -> WatchRequest:
    return WatchRequest(
        TargetSelection(TargetMode.ALL),
        WatchOptions(real_env=real_env, args=args, headers=headers),
    )


def test_local_pipeline_coverage_and_cleanup() -> None:
    local = Local(
        result=LocalRun(
            "PARTIAL",
            "partial",
            "raw",
            {"file": "COMPLETE", "bad": "wat"},
            ("diag",),
        )
    )
    spans, events, declared, authority, rules, mcp = [
        Stage(value) for value in ("span", "event", "decl", "auth", "finding", "driven")
    ]
    dependencies = WatchDependencies(
        Inventory(Target("local")),
        local=local,
        decoy=Decoy(),
        spans=spans,
        events=events,
        declared=declared,
        authority=authority,
        rules=rules,
        mcp=mcp,
        environment={"ENV": "1"},
    )
    outcome = WatchStages(dependencies).run(request(real_env=True, args=("a",), headers=("X",)))[0]
    assert outcome.status == "PARTIAL"
    assert outcome.reason == "partial"
    assert outcome.findings == ("finding",)
    assert outcome.persistence == ("span", "event", "auth")
    assert outcome.coverage["bad"].value == "UNKNOWN"
    assert local.cleaned == 1
    assert local.target is not None and local.target.env["TOKEN"] == "secret"


def test_target_guard_outcomes_and_cancellation() -> None:
    targets = (
        Target("destructive", destructive=True),
        Target("missing", command=None),
        Target("remote", transport="http"),
    )
    outcome = WatchStages(
        WatchDependencies(Inventory(*targets), local=Local(False), cancellation=Cancel())
    ).run(request(real_env=True))[0]
    assert (outcome.status, outcome.reason) == ("INCOMPLETE", "CANCELLED")
    outcome = WatchStages(WatchDependencies(Inventory(targets[0]), local=Local(True))).run(
        request(real_env=True)
    )[0]
    assert (outcome.status, outcome.reason) == ("SKIPPED", "SKIPPED_DESTRUCTIVE")
    outcome = WatchStages(WatchDependencies(Inventory(targets[1]), local=Local(True))).run(
        request()
    )[0]
    assert outcome.reason == "UNINSTRUMENTABLE_LOCAL_TARGET"
    outcome = WatchStages(WatchDependencies(Inventory(targets[2]))).run(request())[0]
    assert outcome.reason == "UNSUPPORTED_TRANSPORT"
    outcome = WatchStages(WatchDependencies(Inventory(Target("none")))).run(request())[0]
    assert outcome.reason == "RUNTIME_UNAVAILABLE"


def test_remote_pipeline_and_failure_cleanup() -> None:
    remote = Remote(
        RemoteRun("COMPLETE", "ok", "evidence", {"file": "COMPLETE", "process": "PARTIAL"})
    )
    stage = Stage("candidate")
    outcome = WatchStages(
        WatchDependencies(
            Inventory(Target("r", transport="http", url="u")),
            remote=remote,
            rules=stage,
        )
    ).run(request(headers=("Auth",)))[0]
    assert outcome.status == "COMPLETE"
    assert outcome.coverage["file"].value == "UNSUPPORTED"
    assert outcome.coverage["process"].value == "UNSUPPORTED"
    assert remote.closed == 1 and stage.calls == 1

    class Boom(Local):
        def run(
            self,
            target: LocalTarget,
            *,
            timeout: float,
            read_only: bool,
            env: Mapping[str, str],
        ) -> LocalRun:
            raise TimeoutError

    local = Boom(True)
    outcome = WatchStages(WatchDependencies(Inventory(Target("x")), local=local)).run(request())[0]
    assert (outcome.status, outcome.reason) == ("INCOMPLETE", "TIMEOUT")
    assert local.cleaned == 1


@pytest.mark.parametrize("error", (RuntimeError, TypeError, ValueError))
def test_local_stage_errors_become_crash_and_cleanup(error: type[Exception]) -> None:
    class Broken(Local):
        def run(
            self,
            target: LocalTarget,
            *,
            timeout: float,
            read_only: bool,
            env: Mapping[str, str],
        ) -> LocalRun:
            raise error("boom")

    local = Broken(True)
    outcome = WatchStages(WatchDependencies(Inventory(Target("broken")), local=local)).run(
        request()
    )[0]
    assert (outcome.status, outcome.reason) == ("INCOMPLETE", "CRASH")
    assert local.cleaned == 1
