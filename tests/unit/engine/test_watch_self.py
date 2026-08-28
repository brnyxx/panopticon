from __future__ import annotations

from pathlib import Path

from panopticon.engine.watch_self import resolve_self_command


def test_resolves_explicit_toml_command(tmp_path: Path) -> None:
    (tmp_path / "panopticon.toml").write_text(
        '[watch]\ncommand = ["python3", "/self/server.py"]\n',
        encoding="utf-8",
    )

    assert resolve_self_command(tmp_path) == ("python3", "/self/server.py")


def test_resolves_single_node_binary_and_rejects_traversal(tmp_path: Path) -> None:
    package = tmp_path / "package.json"
    package.write_text(
        '{"name":"fixture","bin":{"fixture":"dist/server.mjs"}}',
        encoding="utf-8",
    )
    assert resolve_self_command(tmp_path) == ("node", "/self/dist/server.mjs")

    package.write_text('{"name":"fixture","bin":"../server.mjs"}', encoding="utf-8")
    assert resolve_self_command(tmp_path) is None


def test_malformed_project_files_are_typed_as_absent(tmp_path: Path) -> None:
    (tmp_path / "panopticon.toml").write_text("[watch", encoding="utf-8")
    (tmp_path / "package.json").write_text("{", encoding="utf-8")

    assert resolve_self_command(tmp_path) is None
