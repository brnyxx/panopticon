"""Live production local-watch persistence coverage."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from panopticon.discovery.base import DiscoveryEnv
from panopticon.engine.watch_behavior import apply_behavior_rules
from panopticon.engine.watch_inventory import ProductionWatchInventory
from panopticon.engine.watch_local_model import LocalWatchStatus
from panopticon.engine.watch_local_production import LocalRuntime, run_local_production
from panopticon.engine.watch_model import TargetMode, TargetSelection, WatchOptions
from panopticon.engine.watch_observation import build_watch_observation
from panopticon.models.event import FileEvent, LeakEvent, ProcessEvent
from panopticon.models.ids import derive_span_id
from panopticon.sandbox.docker import DockerRuntime
from panopticon.sandbox.podman import PodmanRuntime
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
    assert str(Path.home()) not in built.observation.model_dump_json()
    loaded = repository.load_observation(persisted.target)
    assert loaded.status is LoadStatus.AVAILABLE
    assert loaded.observation == built.observation
    assert await _running(runtime.executable) == before


@pytest.mark.docker
async def test_real_rootless_podman_watch_is_observed_and_cleaned_up(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    runtime: LocalRuntime = PodmanRuntime()
    assert runtime.available()
    before = await _running(runtime.executable)
    context = (
        ProductionWatchInventory(
            DiscoveryEnv(tmp_path, root, "darwin"),
            self_command=("python3", "/self/tests/fixtures/mcp/clean/file_read.py"),
        )
        .select(TargetSelection(TargetMode.SELF))
        .contexts[0]
    )

    result = await run_local_production(
        context,
        WatchOptions(calls=1, timeout=20, offline=True),
        runtime=runtime,
        self_source=root,
    )

    assert result.status is LocalWatchStatus.COMPLETE
    assert result.coverage["dns"].value == "UNSUPPORTED"
    assert result.coverage["proxy"].value == "UNSUPPORTED"
    assert await _running(runtime.executable) == before


@pytest.mark.docker
async def test_response_leak_persists_only_decoy_key_and_sink(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    runtime: LocalRuntime = DockerRuntime()
    inventory = ProductionWatchInventory(
        DiscoveryEnv(tmp_path, root, "darwin"),
        self_command=("python3", "/self/tests/fixtures/mcp/evil/decoy_leak.py"),
    )
    context = inventory.select(TargetSelection(TargetMode.SELF)).contexts[0]
    result = await run_local_production(
        context,
        WatchOptions(calls=1, timeout=20, offline=True),
        runtime=runtime,
        self_source=root,
    )
    built = build_watch_observation(result)
    assert built.observation is not None
    leaks = [
        event.root
        for span in built.observation.spans
        for event in span.events
        if isinstance(event.root, LeakEvent)
    ]
    assert all(event.sink in {"stderr", "notification", "response"} for event in leaks)
    assert all("PANO_DECOY_VALUE" not in event.decoy_key for event in leaks)
    encoded = built.observation.model_dump_json()
    assert "fixture-decoy-value" not in encoded
    assert str(Path.home()) not in encoded


FIXTURE_MANIFEST = Path(__file__).parents[1] / "fixtures/rules/behavior/expected_sets.json"
_MATRIX = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
_CASES = tuple((group, case) for group in ("evil", "clean") for case in _MATRIX[group])


@pytest.mark.docker
@pytest.mark.parametrize(("group", "case"), _CASES, ids=[f"{g}-{c['name']}" for g, c in _CASES])
async def test_fixture_manifest_paths_produce_exact_registered_findings(
    tmp_path: Path, group: str, case: dict[str, object]
) -> None:
    root = Path(__file__).parents[2]
    script = root / "tests/fixtures/mcp" / group / f"{case['name'].replace('-', '_')}.py"
    context = (
        ProductionWatchInventory(
            DiscoveryEnv(tmp_path, root, "darwin"),
            self_command=("python3", f"/self/tests/fixtures/mcp/{group}/{script.name}"),
        )
        .select(TargetSelection(TargetMode.SELF))
        .contexts[0]
    )
    result = await run_local_production(
        context,
        WatchOptions(calls=1, timeout=20, offline=True),
        runtime=DockerRuntime(),
        self_source=root,
    )
    built = build_watch_observation(result)
    if expected_status := case.get("production_status"):
        assert result.status.value == expected_status
        assert built.observation is None
        assert built.reason_code == "EVIDENCE_INCOMPLETE"
        assert built.diagnostics
        return
    assert built.observation is not None and built.uncovered_events == 0
    assert built.observation.declared.completeness.value == (
        "PARTIAL" if group == "evil" else "COMPLETE"
    )
    behavior = apply_behavior_rules(result, built)
    assert behavior is not None
    expected = {
        (item["id"], item["kind"], item["state"]) for item in case.get("production_expected", [])
    }
    actual = {
        (finding.rule_id, finding.kind.value, "MATCH") for finding in behavior.observation.findings
    }
    assert actual == expected
    if group == "clean":
        assert not any(f.kind.value == "confirmed" for f in behavior.observation.findings)


@pytest.mark.docker
@pytest.mark.parametrize(
    "mode",
    ("decoy_leak_base64", "decoy_leak_url_encoded", "decoy_leak_form_encoded"),
)
async def test_live_encoded_leaks_resolve_to_exact_response_keys(
    tmp_path: Path,
    mode: str,
) -> None:
    root = Path(__file__).parents[2]
    context = (
        ProductionWatchInventory(
            DiscoveryEnv(tmp_path, root, "darwin"),
            self_command=("python3", "/self/tests/fixtures/mcp/python_server.py", mode),
        )
        .select(TargetSelection(TargetMode.SELF))
        .contexts[0]
    )
    result = await run_local_production(
        context,
        WatchOptions(calls=1, timeout=20, offline=True),
        runtime=DockerRuntime(),
        self_source=root,
    )
    built = build_watch_observation(result)

    assert built.observation is not None and result.manifest is not None
    leaks = [
        event.root
        for span in built.observation.spans
        for event in span.events
        if isinstance(event.root, LeakEvent)
    ]
    assert leaks and {leak.sink for leak in leaks} == {"response"}
    assert {leak.decoy_key for leak in leaks} <= {marker.key for marker in result.manifest.markers}
    rendered = built.observation.model_dump_json()
    assert all(marker.text not in rendered for marker in result.manifest.markers)


@pytest.mark.docker
@pytest.mark.parametrize(
    ("mode", "event_type"),
    (("file_write", FileEvent), ("exec_arg", ProcessEvent)),
)
async def test_live_file_and_exec_sinks_keep_only_decoy_metadata(
    tmp_path: Path,
    mode: str,
    event_type: type[FileEvent] | type[ProcessEvent],
) -> None:
    root = Path(__file__).parents[2]
    context = (
        ProductionWatchInventory(
            DiscoveryEnv(tmp_path, root, "darwin"),
            self_command=("python3", "/self/tests/fixtures/mcp/python_server.py", mode),
        )
        .select(TargetSelection(TargetMode.SELF))
        .contexts[0]
    )
    result = await run_local_production(
        context,
        WatchOptions(calls=1, timeout=20, offline=True),
        runtime=DockerRuntime(),
        self_source=root,
    )
    built = build_watch_observation(result)

    assert built.observation is not None and result.manifest is not None
    events = [
        event.root
        for span in built.observation.spans
        for event in span.events
        if isinstance(event.root, event_type)
    ]
    assert events
    rendered = built.observation.model_dump_json()
    assert all(marker.text not in rendered for marker in result.manifest.markers)


@pytest.mark.docker
@pytest.mark.parametrize(
    ("mode", "expected_sinks"),
    (
        ("decoy_leak_stderr", {"stderr"}),
        ("decoy_leak_notification", {"notification", "response"}),
    ),
)
async def test_live_stdio_leak_sinks_are_attributed(
    tmp_path: Path,
    mode: str,
    expected_sinks: set[str],
) -> None:
    root = Path(__file__).parents[2]
    context = (
        ProductionWatchInventory(
            DiscoveryEnv(tmp_path, root, "darwin"),
            self_command=("python3", "/self/tests/fixtures/mcp/python_server.py", mode),
        )
        .select(TargetSelection(TargetMode.SELF))
        .contexts[0]
    )
    result = await run_local_production(
        context,
        WatchOptions(calls=1, timeout=20, offline=True),
        runtime=DockerRuntime(),
        self_source=root,
    )
    built = build_watch_observation(result)

    assert built.observation is not None
    leaks = {
        event.root.sink
        for span in built.observation.spans
        for event in span.events
        if isinstance(event.root, LeakEvent)
    }
    assert leaks == expected_sinks
