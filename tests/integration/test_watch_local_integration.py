"""Live production local-watch persistence coverage."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from panopticon.discovery.base import DiscoveryEnv
from panopticon.engine.watch_inventory import ProductionWatchInventory
from panopticon.engine.watch_local_model import LocalWatchStatus
from panopticon.engine.watch_local_production import LocalRuntime, run_local_production
from panopticon.engine.watch_model import TargetMode, TargetSelection, WatchOptions
from panopticon.engine.watch_observation import build_watch_observation
from panopticon.models.ids import derive_span_id
from panopticon.sandbox.docker import DockerRuntime
from panopticon.store.contracts import PersistSuccess
from panopticon.store.repository import ArtifactRepository, LoadStatus


async def _running(executable: str) -> frozenset[str]:
    process = await asyncio.create_subprocess_exec(
        executable,
        "ps",
        "--format",
        "{{.ID}}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()
    assert process.returncode == 0
    return frozenset(stdout.decode().splitlines())


@pytest.mark.docker
async def test_real_python_mcp_is_observed_and_cleaned_up(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    runtime: LocalRuntime = DockerRuntime()
    before = await _running(runtime.executable)
    inventory = ProductionWatchInventory(
        DiscoveryEnv(tmp_path, root, "darwin"),
        self_command=("python3", "/self/tests/fixtures/mcp/evil/file_read.py"),
    )
    context = inventory.select(TargetSelection(TargetMode.SELF)).contexts[0]

    result = await run_local_production(
        context,
        WatchOptions(calls=1, timeout=20, offline=True),
        runtime=runtime,
        self_source=root,
    )

    assert result.status is LocalWatchStatus.COMPLETE
    assert result.protocol is not None and result.protocol.server_name == "panopticon-fixture"
    assert [tool.name for tool in result.tools] == ["file_read"]
    call = next(span for span in result.spans if span.tool == "file_read")
    assert call.span_id == derive_span_id("file_read", 1)
    assert result.trace is not None and result.trace.events
    assert any(event.path and event.path.startswith("/home/pano/") for event in result.trace.events)
    assert result.notifications and result.notifications[0]["method"] == (
        "notifications/fixture/ready"
    )
    built = build_watch_observation(result)
    assert built.observation is not None and built.uncovered_events == 0
    repository = ArtifactRepository(tmp_path / "store")
    persisted = repository.persist_observation(built.observation)
    assert isinstance(persisted, PersistSuccess)
    loaded = repository.load_observation(persisted.target)
    assert loaded.status is LoadStatus.AVAILABLE
    assert loaded.observation == built.observation
    assert await _running(runtime.executable) == before
