"""OMO-41 fixed-workload performance contracts."""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))
performance_gate = importlib.import_module("scripts.performance_gate")
FIXTURE_VERSION = performance_gate.FIXTURE_VERSION
SAMPLES = performance_gate.SAMPLES
deterministic_decoys = performance_gate.deterministic_decoys
nearest_rank_p95 = performance_gate.nearest_rank_p95


def test_nearest_rank_requires_thirty_samples() -> None:
    try:
        nearest_rank_p95([1.0] * (SAMPLES - 1))
    except ValueError:
        return
    raise AssertionError("fewer than 30 samples must fail closed")


def test_decoy_generation_is_deterministic_and_bounded() -> None:
    started = time.perf_counter()
    first = deterministic_decoys()
    elapsed = (time.perf_counter() - started) * 1000
    assert first == deterministic_decoys()
    assert FIXTURE_VERSION and elapsed <= 1000
