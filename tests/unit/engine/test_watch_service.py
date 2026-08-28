from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

import panopticon.engine.watch_service as service_module
import panopticon.engine.watch_service_targets as targets_module
from panopticon.discovery.base import DiscoveryEnv
from panopticon.engine.watch_behavior import BehaviorBuild
from panopticon.engine.watch_inventory import WatchTargetContext
from panopticon.engine.watch_local_model import LocalWatchResult, LocalWatchStatus
from panopticon.engine.watch_local_runtime import LocalRuntime
from panopticon.engine.watch_model import TargetMode, TargetSelection, WatchOptions, WatchRequest
from panopticon.engine.watch_observation import WatchObservationBuild
from panopticon.engine.watch_remote_production import RemoteWatchResult
from panopticon.engine.watch_service import WatchInputs, run_watch_service
from panopticon.models.observation import Observation
from panopticon.store.contracts import PersistRejected, RejectionCode, SinkKind
from panopticon.store.repository import ArtifactRepository

FIXTURE = Path("tests/fixtures/schemas/observation.json")


def _config(home: Path, *, remote: bool) -> None:
    path = home / "Library/Application Support/Claude/claude_desktop_config.json"
    path.parent.mkdir(parents=True)
    entry: dict[str, object] = (
        {"url": "https://api.example.test/mcp"}
        if remote
        else {"command": "node", "args": ["server.mjs"]}
    )
    path.write_text(json.dumps({"mcpServers": {"target": entry}}), encoding="utf-8")


def _observation() -> Observation:
    return Observation.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def test_service_normalizes_internal_diagnostics_without_payloads() -> None:
    diagnostic = service_module._diagnostic("lowercase", "")

    assert diagnostic.code == "WATCH_STAGE"
    assert diagnostic.detail == "WATCH_STAGE"


@pytest.mark.asyncio
async def test_service_keeps_missing_and_unsupported_selection_typed(tmp_path: Path) -> None:
    inputs = WatchInputs(
        DiscoveryEnv(tmp_path, tmp_path, "darwin"),
        ArtifactRepository(tmp_path / "store"),
    )

    missing = await run_watch_service(
        WatchRequest(TargetSelection(TargetMode.NAME, "missing")),
        inputs,
    )
    unsupported = await run_watch_service(
        WatchRequest(TargetSelection(TargetMode.SELF)),
        inputs,
    )

    assert missing.result.status.value == "INCOMPLETE"
    assert unsupported.result.status.value == "UNSUPPORTED"


@pytest.mark.asyncio
async def test_service_persists_remote_without_selecting_local_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _config(tmp_path, remote=True)

    async def remote(
        context: WatchTargetContext,
        options: WatchOptions,
    ) -> RemoteWatchResult:
        return RemoteWatchResult(
            LocalWatchStatus.COMPLETE,
            "OK",
            _observation(),
            ("authorized-secret",),
        )

    monkeypatch.setattr(targets_module, "run_remote_production", remote)
    outcome = await run_watch_service(
        WatchRequest(TargetSelection(TargetMode.NAME, "target")),
        WatchInputs(
            DiscoveryEnv(tmp_path, tmp_path, "darwin"),
            ArtifactRepository(tmp_path / "store"),
        ),
    )

    assert outcome.targets[0].reason_code == "OBSERVATION_PERSISTED"

    assert tuple((tmp_path / "store" / "observations").rglob("*.json"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "reason"),
    (
        (LocalWatchStatus.UNSUPPORTED, "ADDRESS_BLOCKED"),
        (LocalWatchStatus.INCOMPLETE, "TIMEOUT"),
    ),
)
async def test_service_preserves_remote_failure_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    status: LocalWatchStatus,
    reason: str,
) -> None:
    _config(tmp_path, remote=True)

    async def remote(
        context: WatchTargetContext,
        options: WatchOptions,
    ) -> RemoteWatchResult:
        return RemoteWatchResult(status, reason)

    monkeypatch.setattr(targets_module, "run_remote_production", remote)
    outcome = await run_watch_service(
        WatchRequest(TargetSelection(TargetMode.NAME, "target")),
        WatchInputs(
            DiscoveryEnv(tmp_path, tmp_path, "darwin"),
            ArtifactRepository(tmp_path / "store"),
        ),
    )

    assert outcome.targets[0].status == status.value
    assert outcome.targets[0].reason_code == reason


@pytest.mark.asyncio
async def test_service_reports_png_persistence_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _config(tmp_path, remote=True)

    async def remote(
        context: WatchTargetContext,
        options: WatchOptions,
    ) -> RemoteWatchResult:
        return RemoteWatchResult(LocalWatchStatus.COMPLETE, "OK", _observation())

    def reject(repository: ArtifactRepository, observation: Observation) -> PersistRejected:
        return PersistRejected(
            repository.root / "card.png",
            SinkKind.PNG,
            RejectionCode.LEAK_DETECTED,
        )

    monkeypatch.setattr(targets_module, "run_remote_production", remote)
    monkeypatch.setattr(targets_module, "persist_observation_png", reject)
    outcome = await run_watch_service(
        WatchRequest(
            TargetSelection(TargetMode.NAME, "target"),
            WatchOptions(png=True),
        ),
        WatchInputs(
            DiscoveryEnv(tmp_path, tmp_path, "darwin"),
            ArtifactRepository(tmp_path / "store"),
        ),
    )

    assert outcome.targets[0].reason_code == "PNG_PERSIST_FAILED"


@pytest.mark.asyncio
async def test_service_persists_local_composed_observation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _config(tmp_path, remote=False)
    observation = _observation()

    async def local(
        context: WatchTargetContext,
        options: WatchOptions,
        **kwargs: object,
    ) -> LocalWatchResult:
        return LocalWatchResult(context, LocalWatchStatus.COMPLETE, "OK")

    def build(result: LocalWatchResult, *, raw: bool = False) -> WatchObservationBuild:
        assert not raw
        return WatchObservationBuild(observation, 0)

    def behavior(
        result: LocalWatchResult,
        built: WatchObservationBuild,
    ) -> BehaviorBuild:
        return BehaviorBuild(observation)

    monkeypatch.setattr(targets_module, "run_local_production", local)
    monkeypatch.setattr(targets_module, "build_watch_observation", build)
    monkeypatch.setattr(targets_module, "apply_behavior_rules", behavior)
    outcome = await run_watch_service(
        WatchRequest(TargetSelection(TargetMode.NAME, "target")),
        WatchInputs(
            DiscoveryEnv(tmp_path, tmp_path, "darwin"),
            ArtifactRepository(tmp_path / "store"),
            runtime=cast(LocalRuntime, object()),
        ),
    )

    assert outcome.targets[0].reason_code == "OBSERVATION_PERSISTED"

    async def incomplete_local(
        context: WatchTargetContext,
        options: WatchOptions,
        **kwargs: object,
    ) -> LocalWatchResult:
        return LocalWatchResult(context, LocalWatchStatus.INCOMPLETE, "TIMEOUT")

    monkeypatch.setattr(targets_module, "run_local_production", incomplete_local)
    incomplete = await run_watch_service(
        WatchRequest(TargetSelection(TargetMode.NAME, "target")),
        WatchInputs(
            DiscoveryEnv(tmp_path, tmp_path, "darwin"),
            ArtifactRepository(tmp_path / "other-store"),
            runtime=cast(LocalRuntime, object()),
        ),
    )
    assert incomplete.targets[0].reason_code == "TIMEOUT"

    def no_behavior(
        result: LocalWatchResult,
        built: WatchObservationBuild,
    ) -> None:
        return None

    monkeypatch.setattr(targets_module, "run_local_production", local)
    monkeypatch.setattr(targets_module, "apply_behavior_rules", no_behavior)
    missing_behavior = await run_watch_service(
        WatchRequest(TargetSelection(TargetMode.NAME, "target")),
        WatchInputs(
            DiscoveryEnv(tmp_path, tmp_path, "darwin"),
            ArtifactRepository(tmp_path / "third-store"),
            runtime=cast(LocalRuntime, object()),
        ),
    )
    assert missing_behavior.targets[0].reason_code == "OK"
