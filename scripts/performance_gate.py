#!/usr/bin/env python3
"""Fail-closed product performance harness with a frozen local workload."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

from panopticon.discovery import registered_adapters
from panopticon.discovery.base import DiscoveryEnv
from panopticon.engine.doctor import DoctorInputs, run_doctor
from panopticon.engine.doctor_model import DoctorRequest
from panopticon.engine.watch_local import LocalRun, LocalTarget
from panopticon.engine.watch_model import (
    TargetMode,
    TargetSelection,
    WatchOptions,
    WatchRequest,
    WatchTarget,
)
from panopticon.engine.watch_stages import WatchDependencies, WatchStages
from panopticon.sandbox.decoy import decoy_archive, generate_decoy_home
from panopticon.util.leak_check import LeakContext, find_leaks
from panopticon.wrap.relay import relay

SAMPLES = 30
FIXTURE_VERSION = "omo-41-v1"
_LIMITS = {
    "doctor_warm_p95_ms": 5_000.0,
    "watch_warm_p95_ms": 60_000.0,
    "decoy_p95_ms": 1_000.0,
    "wrap_relay_added_p95_ms": 1.0,
}


class Workloads(TypedDict):
    doctor_cold_ms: float
    doctor_warm_p95_ms: float
    watch_warm_p95_ms: float
    decoy_p95_ms: float
    wrap_relay_added_p95_ms: float


class PerformanceEvidence(TypedDict):
    schema_version: int
    fixture_version: str
    samples: int
    hardware_class: str
    os: str
    runtime: str
    image_lock_sha256: str
    cache_state: str
    workloads: Workloads
    limits_ms: dict[str, float]
    artifact_sizes: dict[str, int]
    status: str


def nearest_rank_p95(values: Sequence[float]) -> float:
    if len(values) < SAMPLES:
        raise ValueError("PERFORMANCE_SAMPLE_COUNT_INSUFFICIENT")
    ordered = sorted(values)
    rank = (95 * len(ordered) + 99) // 100
    return ordered[rank - 1]


def deterministic_decoys() -> bytes:
    manifest = generate_decoy_home(FIXTURE_VERSION, "performance-fixture")
    return decoy_archive(manifest)


def _measure(workload: Callable[[], object], count: int = SAMPLES) -> list[float]:
    values: list[float] = []
    for _ in range(count):
        started = time.perf_counter()
        workload()
        values.append((time.perf_counter() - started) * 1_000)
    return values


class _Reader:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def read(self, size: int = -1) -> bytes:
        payload, self._payload = self._payload, b""
        return payload


class _Writer:
    def __init__(self) -> None:
        self.data = bytearray()

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


def _relay_once() -> None:
    payload = b"x" * 8_192
    left = _Writer()
    right = _Writer()
    asyncio.run(relay(_Reader(payload), left, _Reader(payload), right))
    if left.data != payload or right.data != payload:
        raise RuntimeError("WRAP_RELAY_CORRUPTED")


def _async_baseline() -> None:
    asyncio.run(asyncio.sleep(0))


@dataclass(frozen=True, slots=True)
class _Target:
    name: str = "performance-fixture"
    transport: str = "stdio"
    destructive: bool = False
    command: str | None = "fixture"
    args: tuple[str, ...] = ()
    url: str | None = None


class _Inventory:
    def select(self, selection: TargetSelection) -> tuple[WatchTarget, ...]:
        return (cast(WatchTarget, _Target()),)


class _LocalRuntime:
    def available(self) -> bool:
        return True

    def run(
        self,
        target: LocalTarget,
        *,
        timeout: float,
        read_only: bool,
        env: Mapping[str, str],
    ) -> LocalRun:
        return LocalRun("COMPLETE", "FIXTURE_COMPLETE", b"fixture", {"stdio": "COMPLETE"})

    def cleanup(self) -> None:
        return None


def _watch_once() -> None:
    outcome = WatchStages(WatchDependencies(_Inventory(), local=_LocalRuntime())).run(
        WatchRequest(TargetSelection(TargetMode.ALL), WatchOptions())
    )
    if len(outcome) != 1 or outcome[0].status != "COMPLETE":
        raise RuntimeError("WATCH_FIXTURE_INCOMPLETE")


def _doctor_workload(root: Path, home: Path) -> Callable[[], None]:
    environment = DiscoveryEnv(home, root, platform.system().casefold())
    inputs = DoctorInputs(environment, registered_adapters(environment))

    def run() -> None:
        outcome = run_doctor(DoctorRequest(list_clients=True, offline=True), inputs)
        if outcome.result.status.value not in {"COMPLETE", "PARTIAL"}:
            raise RuntimeError("DOCTOR_FIXTURE_INCOMPLETE")

    return run


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root: Path, output: Path) -> PerformanceEvidence:
    with tempfile.TemporaryDirectory(prefix="pano-performance-") as directory:
        home = Path(directory)
        doctor = _doctor_workload(root, home)
        cold = _measure(doctor, 1)[0]
        doctor_samples = _measure(doctor)
    decoy_samples = _measure(deterministic_decoys)
    watch_samples = _measure(_watch_once)
    baseline_samples = _measure(_async_baseline)
    relay_samples = _measure(_relay_once)
    added = [
        max(0.0, relay_time - baseline_time)
        for relay_time, baseline_time in zip(
            relay_samples,
            baseline_samples,
            strict=True,
        )
    ]
    decoys = deterministic_decoys()
    workloads: Workloads = {
        "doctor_cold_ms": cold,
        "doctor_warm_p95_ms": nearest_rank_p95(doctor_samples),
        "watch_warm_p95_ms": nearest_rank_p95(watch_samples),
        "decoy_p95_ms": nearest_rank_p95(decoy_samples),
        "wrap_relay_added_p95_ms": nearest_rank_p95(added),
    }
    workload_values = {
        "doctor_warm_p95_ms": workloads["doctor_warm_p95_ms"],
        "watch_warm_p95_ms": workloads["watch_warm_p95_ms"],
        "decoy_p95_ms": workloads["decoy_p95_ms"],
        "wrap_relay_added_p95_ms": workloads["wrap_relay_added_p95_ms"],
    }
    passed = all(
        workload_values.get(name, float("inf")) <= limit for name, limit in _LIMITS.items()
    )
    evidence: PerformanceEvidence = {
        "schema_version": 1,
        "fixture_version": FIXTURE_VERSION,
        "samples": SAMPLES,
        "hardware_class": f"{platform.machine()}-{os.cpu_count() or 0}cpu",
        "os": platform.platform(),
        "runtime": platform.python_version(),
        "image_lock_sha256": _file_sha256(root / "src/panopticon/sandbox/images.lock"),
        "cache_state": "one-cold-then-warm",
        "workloads": workloads,
        "limits_ms": dict(_LIMITS),
        "artifact_sizes": {"decoy_archive_bytes": len(decoys), "relay_payload_bytes": 8_192},
        "status": "PASS" if passed else "FAIL",
    }
    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    leaks = find_leaks(encoded, LeakContext(home_paths=(str(Path.home()),)))
    if leaks:
        raise RuntimeError("PERFORMANCE_EVIDENCE_LEAK")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(encoded + "\n", encoding="utf-8")
    temporary.replace(output)
    if not passed:
        raise RuntimeError("PERFORMANCE_LIMIT_EXCEEDED")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    collect(Path.cwd(), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
