"""Deterministic foundation fixtures behind the thin CLI wrappers."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from panopticon.discovery.base import DiscoveryEnv
from panopticon.engine.contracts import (
    EngineDiagnostic,
    EngineReason,
    Result,
    UnsupportedResult,
)
from panopticon.engine.diff import DiffRequest
from panopticon.engine.diff import run_diff as _run_diff
from panopticon.engine.doctor import DoctorInputs, DoctorRequest
from panopticon.engine.doctor import run_doctor as _run_doctor
from panopticon.engine.doctor_model import DoctorOutcome
from panopticon.engine.scan import ScanRequest
from panopticon.engine.watch import (
    TargetMode,
    TargetSelection,
    WatchOptions,
    WatchRequest,
)
from panopticon.engine.watch_self import resolve_self_command
from panopticon.engine.watch_service import WatchInputs, WatchServiceOutcome, run_watch_service
from panopticon.registry.cache import PersistentCache
from panopticon.registry.client import RegistryClient
from panopticon.registry.http import HttpxRegistryHttp, SystemClock
from panopticon.registry.provider import RegistryProvider
from panopticon.store.repository import ArtifactRepository
from panopticon.util.leak_check import LeakContext


def _not_implemented(epic: str) -> UnsupportedResult:
    return UnsupportedResult(
        reason_code=EngineReason.UNSUPPORTED_TRANSPORT,
        diagnostics=(EngineDiagnostic("NOT_IMPLEMENTED", epic),),
    )


def run_doctor(request: DoctorRequest) -> Result:
    return doctor_outcome(request).result


def doctor_outcome(request: DoctorRequest) -> DoctorOutcome:
    """Run doctor with process runtime dependencies for the CLI boundary."""
    platform = "darwin" if sys.platform == "darwin" else "windows" if os.name == "nt" else "linux"
    env = DiscoveryEnv(Path.home(), Path.cwd(), platform, dict(os.environ))
    home = Path.home()
    token = os.environ.get("GITHUB_TOKEN")
    repository = ArtifactRepository(
        home / ".panopticon",
        LeakContext(home_paths=(str(home),), secrets=(token,) if token else ()),
    )
    clock = SystemClock()
    provider = RegistryProvider(
        PersistentCache(repository),
        RegistryClient(HttpxRegistryHttp(), clock, github_token=token),
    )
    return asyncio.run(_run_doctor(request, inputs=DoctorInputs(env, registry_lookup=provider)))


def run_watch(request: WatchRequest) -> WatchServiceOutcome:
    return watch_outcome(request)


def watch_outcome(request: WatchRequest) -> WatchServiceOutcome:
    """Run watch with process runtime dependencies for the CLI boundary."""
    platform = "darwin" if sys.platform == "darwin" else "windows" if os.name == "nt" else "linux"
    home = Path.home()
    cwd = Path.cwd()
    env = DiscoveryEnv(home, cwd, platform, dict(os.environ))
    repository = ArtifactRepository(
        home / ".panopticon",
        LeakContext(home_paths=(str(home),)),
    )
    self_command = resolve_self_command(cwd) if request.selection.mode is TargetMode.SELF else None
    return asyncio.run(
        run_watch_service(
            request,
            WatchInputs(
                env,
                repository,
                self_command=self_command,
                self_source=cwd if self_command is not None else None,
            ),
        )
    )


def run_diff(request: DiffRequest) -> Result:
    return _run_diff(request).result


def run_scan(request: ScanRequest) -> Result:
    return _not_implemented("E16")


__all__ = [
    "DiffRequest",
    "DoctorRequest",
    "ScanRequest",
    "TargetMode",
    "TargetSelection",
    "WatchOptions",
    "WatchRequest",
    "doctor_outcome",
    "run_diff",
    "run_doctor",
    "run_scan",
    "run_watch",
    "watch_outcome",
]
