"""Release gate command and fail-closed input contracts."""

from __future__ import annotations

import importlib
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))
release_gate = importlib.import_module("scripts.release_gate")
run_argv = release_gate.run_argv
validate_inputs = release_gate.validate_inputs


def test_injected_runner_receives_exact_argv_without_shell() -> None:
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "", "")

    result = run_argv(["make", "ci"], runner)
    assert result["status"] == "PASS"
    assert calls == [
        (
            ["make", "ci"],
            {
                "cwd": None,
                "shell": False,
                "capture_output": True,
                "text": True,
                "check": False,
            },
        )
    ]


def test_stale_leaky_slow_or_skipped_inputs_fail_gate() -> None:
    now = time.time()
    cases = [
        {"status": "PASS", "timestamp": now - 90000},
        {"status": "PASS", "timestamp": now, "leak": True},
        {"status": "PASS", "timestamp": now, "duration_ms": 101, "limit_ms": 100},
        {"status": "PASS", "timestamp": now, "skipped": True},
    ]
    for item in cases:
        with pytest.raises(ValueError):
            validate_inputs([item], now=now)
