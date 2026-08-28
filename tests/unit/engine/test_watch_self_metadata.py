from __future__ import annotations

import json
from pathlib import Path

import pytest

import panopticon.engine.watch_self_metadata as metadata
from panopticon.discovery.base import DiscoveryEnv
from panopticon.engine.watch_inventory import InventoryStatus, ProductionWatchInventory
from panopticon.engine.watch_model import TargetMode, TargetSelection


def test_readme_manifest_and_yaml_are_parsed_and_filenames_sorted(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Привет\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name":"demo","engines":{"node":">=20"}}')
    (tmp_path / ".panopticon.yaml").write_text("watch:\n  enabled: true\n", encoding="utf-8")
    (tmp_path / "z.txt").write_text("z", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")

    result = metadata.acquire_self_metadata(tmp_path)

    assert result["readme"] == "# Привет\n"
    assert result["manifest"] == {"name": "demo", "engines": {"node": ">=20"}}
    assert result["config"] == {"watch": {"enabled": True}}
    assert result["project_filenames"] == [
        ".panopticon.yaml",
        "README.md",
        "a.txt",
        "package.json",
        "z.txt",
    ]


def test_pyproject_toml_and_readme_name_fallbacks(tmp_path: Path) -> None:
    (tmp_path / "README.rst").write_text("Project", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")

    result = metadata.acquire_self_metadata(tmp_path)

    assert result["readme"] == "Project"
    assert result["manifest"] == {"project": {"name": "demo"}}


def test_malformed_and_oversize_files_are_visible_as_typed_absent_or_raw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "README.md").write_bytes(b"\xff\xfe")
    (tmp_path / "package.json").write_text("{not json", encoding="utf-8")
    (tmp_path / ".panopticon.yaml").write_text("watch:\n  enabled: true\n", encoding="utf-8")
    monkeypatch.setattr(metadata, "_MAX_MANIFEST", 10)

    result = metadata.acquire_self_metadata(tmp_path)

    assert result["readme"] == 0
    assert result["manifest"] == "{not json"
    assert result["config"] == 0


def test_yaml_conversion_error_returns_original_text(tmp_path: Path) -> None:
    config = tmp_path / ".panopticon.yaml"
    config.write_text("!!set {a, b}", encoding="utf-8")

    result = metadata.acquire_self_metadata(tmp_path)

    assert result["config"] == "!!set {a, b}"


def test_json_conversion_error_returns_original_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "package.json"
    path.write_text('{"name":"demo"}', encoding="utf-8")
    original_loads = json.loads

    def broken_loads(text: str) -> object:
        value = original_loads(text)
        assert isinstance(value, dict)
        value["bad"] = object()
        return value

    monkeypatch.setattr("panopticon.engine.watch_self_metadata.json.loads", broken_loads)
    result = metadata.acquire_self_metadata(tmp_path)

    assert result["manifest"] == '{"name":"demo"}'


def test_project_files_exclude_symlinks_traversal_and_dependency_directories(
    tmp_path: Path,
) -> None:
    (tmp_path / "kept.txt").write_text("ok", encoding="utf-8")
    outside = tmp_path.parent / "outside-self-metadata.txt"
    outside.write_text("outside", encoding="utf-8")
    try:
        (tmp_path / "link.txt").symlink_to(outside)
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "ignored.txt").write_text("x", encoding="utf-8")
        (tmp_path / "linked-dir").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")

    names = metadata._project_files(tmp_path)

    assert names == ("kept.txt",)


def test_project_files_enforce_depth_and_count_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(metadata, "_MAX_DEPTH", 1)
    monkeypatch.setattr(metadata, "_MAX_FILES", 2)
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "c.txt").write_text("c", encoding="utf-8")
    deep = tmp_path / "level" / "deeper"
    deep.mkdir(parents=True)
    (deep / "hidden.txt").write_text("hidden", encoding="utf-8")

    names = metadata._project_files(tmp_path)

    assert len(names) == 2
    assert names == tuple(sorted(names))
    assert "hidden.txt" not in names


def test_explicit_self_inventory_attaches_metadata_to_raw_entry(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("self project", encoding="utf-8")
    inventory = ProductionWatchInventory(
        DiscoveryEnv(tmp_path, tmp_path, "darwin"), self_command=("python", "server.py")
    )

    selected = inventory.select(TargetSelection(TargetMode.SELF))

    assert selected.status is InventoryStatus.SELECTED
    assert selected.contexts[0].raw_entry.metadata["readme"] == "self project"
    assert selected.contexts[0].raw_entry.raw["project_filenames"] == ["README.md"]
