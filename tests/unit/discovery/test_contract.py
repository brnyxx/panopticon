from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import get_origin, get_type_hints

import pytest

from panopticon.discovery import base
from panopticon.models import ConfigPath, ConfigScope, JsonPointer


def _require_paths_module() -> ModuleType:
    """Load shared discovery traversal at test time so the base stays RED."""
    qualified_name = "panopticon.util.paths"
    try:
        return import_module(qualified_name)
    except ModuleNotFoundError as error:
        if error.name == qualified_name:
            pytest.fail(f"DISCOVERY_CONTRACT_MISSING:{qualified_name}", pytrace=False)
        raise


def test_discovery_entries_carry_task3_identity_and_source_location() -> None:
    # Given: the existing discovery and branded identity contracts.
    entry_fields = {field.name for field in fields(base.RawServerEntry)}
    error_fields = {field.name for field in fields(base.ParseError)}
    entry_annotations = get_type_hints(base.RawServerEntry)

    # When: the extended discovery contract is inspected.
    required_entry_fields = {
        "logical_path",
        "realpath",
        "original_sha256",
        "json_pointer",
        "source_location",
    }
    required_error_fields = {"line", "column", "offset"}

    # Then: entries retain distinct path/hash/location data and reuse Task3 brands.
    assert required_entry_fields <= entry_fields
    assert required_error_fields <= error_fields
    assert entry_annotations["logical_path"] is ConfigPath
    assert entry_annotations["json_pointer"] is JsonPointer
    assert entry_annotations["realpath"] is Path
    assert entry_annotations["original_sha256"] is str
    assert get_origin(entry_annotations["raw"]) is Mapping
    assert entry_annotations["scope"] is ConfigScope


def test_project_traversal_includes_cwd_and_exactly_three_parent_levels(
    tmp_path: Path,
) -> None:
    # Given: a cwd nested beneath more than three possible project roots.
    cwd = tmp_path / "repo" / "one" / "two" / "three" / "cwd"
    cwd.mkdir(parents=True)
    paths = _require_paths_module()
    name = "project_roots"
    assert hasattr(paths, name)

    # When: project roots are enumerated from the injected cwd.
    roots = tuple(getattr(paths, name)(cwd))

    # Then: cwd is nearest and the fourth parent is outside the traversal boundary.
    expected = (cwd, cwd.parent, cwd.parent.parent, cwd.parent.parent.parent)
    assert roots == expected
    assert cwd.parent.parent.parent.parent not in roots
    assert len(roots) == 4


def test_project_traversal_at_filesystem_root_remains_exactly_bounded() -> None:
    # Given: the filesystem root has no distinct parent levels to enumerate.
    paths = _require_paths_module()
    name = "project_roots"
    assert hasattr(paths, name)

    # When: project roots are requested at the root boundary.
    roots = tuple(getattr(paths, name)(Path("/")))

    # Then: the contract remains four entries without indexing beyond the root.
    assert roots == (Path("/"), Path("/"), Path("/"), Path("/"))


def test_candidate_order_is_nearest_project_then_deterministic_global(
    tmp_path: Path,
) -> None:
    # Given: project candidates ordered nearest-to-farthest and duplicate global candidates.
    cwd = tmp_path / "repo" / "service"
    cwd.mkdir(parents=True)
    project = (cwd / "nearest.json", cwd.parent / "parent.json")
    global_paths = (tmp_path / "global-b.json", tmp_path / "global-a.json", project[0])
    paths = _require_paths_module()
    name = "order_candidate_paths"
    assert hasattr(paths, name)
    order = getattr(paths, name)

    # When: the same candidate set is ordered twice with different global input order.
    first = tuple(order(project, global_paths))
    second = tuple(order(project, tuple(reversed(global_paths))))

    # Then: nearest project paths precede sorted global paths with stable duplicate handling.
    assert first == (project[0], project[1], tmp_path / "global-a.json", tmp_path / "global-b.json")
    assert second == first
