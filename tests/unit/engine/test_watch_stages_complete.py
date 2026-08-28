from dataclasses import dataclass

import pytest

from panopticon.engine.watch_local import LocalRun
from panopticon.engine.watch_model import TargetMode, TargetSelection, WatchOptions, WatchRequest
from panopticon.engine.watch_remote import RemoteRun
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
    def __init__(self, *targets):
        self.targets = targets

    def select(self, selection):
        return self.targets


class Local:
    def __init__(self, available=True, run=None):
        self.ok, self.result, self.cleaned, self.args = available, run, 0, None

    def available(self):
        return self.ok

    def run(self, target, **kwargs):
        self.args = (target, kwargs)
        return self.result

    def cleanup(self):
        self.cleaned += 1


class Remote:
    def __init__(self, result):
        self.result, self.closed, self.args = result, 0, None

    def observe(self, target, **kwargs):
        self.args = (target, kwargs)
        return self.result

    def close(self):
        self.closed += 1


class Decoy:
    def manifest(self):
        return {"TOKEN": "secret", "OTHER": "x"}

    def archive(self):
        return b"archive"


class Stage:
    def __init__(self, value):
        self.value, self.calls = value, 0

    def collect(self, evidence):
        self.calls += 1
        return self.value

    def extract(self, evidence):
        self.calls += 1
        return self.value

    def apply(self, value, *, target):
        self.calls += 1
        return self.value

    def evaluate(self, evidence, *, target):
        self.calls += 1
        return (self.value,)

    def drive(self, evidence, **kwargs):
        self.calls += 1
        return self.value


class Cancel:
    def __init__(self, value=True):
        self.value = value

    def cancelled(self):
        return self.value


def request(**kwargs):
    return WatchRequest(TargetSelection(TargetMode.ALL), WatchOptions(**kwargs))


def test_local_pipeline_coverage_and_cleanup():
    local = Local(
        run=LocalRun("PARTIAL", "partial", "raw", {"file": "COMPLETE", "bad": "wat"}, ("diag",))
    )
    spans, events, declared, auth, rules, mcp = [
        Stage(x) for x in ("span", "event", "decl", "auth", "finding", "driven")
    ]
    d = WatchDependencies(
        Inventory(Target("local")),
        local=local,
        decoy=Decoy(),
        spans=spans,
        events=events,
        declared=declared,
        authority=auth,
        rules=rules,
        mcp=mcp,
        environment={"ENV": "1"},
    )
    out = WatchStages(d).run(request(real_env=True, args=("a",), headers=("X",)))[0]
    assert out.status == "PARTIAL" and out.reason == "partial" and out.findings == ("finding",)
    assert out.persistence == ("span", "event", "auth") and out.coverage["bad"].value == "UNKNOWN"
    assert local.cleaned == 1 and local.args[0].env["TOKEN"] == "secret"


def test_target_guard_outcomes_and_cancellation():
    targets = [
        Target("destructive", destructive=True),
        Target("missing", command=None),
        Target("remote", transport="http"),
    ]
    out = WatchStages(
        WatchDependencies(Inventory(*targets), local=Local(False), cancellation=Cancel())
    ).run(request(real_env=True))[0]
    assert (out.status, out.reason) == ("INCOMPLETE", "CANCELLED")
    out = WatchStages(WatchDependencies(Inventory(targets[0]), local=Local(True))).run(
        request(real_env=True)
    )[0]
    assert (out.status, out.reason) == ("SKIPPED", "SKIPPED_DESTRUCTIVE")
    out = WatchStages(WatchDependencies(Inventory(targets[1]), local=Local(True))).run(request())[0]
    assert out.reason == "UNINSTRUMENTABLE_LOCAL_TARGET"
    out = WatchStages(WatchDependencies(Inventory(targets[2]))).run(request())[0]
    assert out.reason == "UNSUPPORTED_TRANSPORT"
    out = WatchStages(WatchDependencies(Inventory(Target("none")), local=None)).run(request())[0]
    assert out.reason == "RUNTIME_UNAVAILABLE"


def test_remote_pipeline_and_failure_cleanup():
    remote = Remote(
        RemoteRun("COMPLETE", "ok", "evidence", {"file": "COMPLETE", "process": "PARTIAL"})
    )
    stage = Stage("candidate")
    out = WatchStages(
        WatchDependencies(
            Inventory(Target("r", transport="http", url="u")), remote=remote, rules=stage
        )
    ).run(request(headers=("Auth",)))[0]
    assert (
        out.status == "COMPLETE"
        and out.coverage["file"].value == "UNSUPPORTED"
        and out.coverage["process"].value == "UNSUPPORTED"
    )
    assert remote.closed == 1 and stage.calls == 1

    class Boom(Local):
        def run(self, *a, **k):
            raise TimeoutError

    local = Boom(True)
    out = WatchStages(WatchDependencies(Inventory(Target("x")), local=local)).run(request())[0]
    assert (out.status, out.reason) == ("INCOMPLETE", "TIMEOUT") and local.cleaned == 1


@pytest.mark.parametrize("error", (RuntimeError, TypeError, ValueError))
def test_local_stage_errors_become_crash_and_cleanup(error):
    class Broken(Local):
        def run(self, *args, **kwargs):
            raise error("boom")

    local = Broken(True)
    out = WatchStages(WatchDependencies(Inventory(Target("broken")), local=local)).run(request())[0]
    assert (out.status, out.reason) == ("INCOMPLETE", "CRASH")
    assert local.cleaned == 1
