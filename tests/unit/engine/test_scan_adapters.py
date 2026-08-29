from __future__ import annotations

from pathlib import Path

from panopticon.analyzers.static.model import ScannerConfig, SourceRange, StaticMatch
from panopticon.engine.scan import ScanConfig, ScanMode
from panopticon.engine.scan_adapters import ProductionSemgrep, build_scan_request


def test_production_semgrep_delegates_config_files_rules_and_pinned_runner(
    monkeypatch, tmp_path: Path
) -> None:
    config = ScanConfig(
        ScanMode.STANDARD,
        ScannerConfig(selected_rule_ids=("SENT-002",), ignore_paths=("ignored.py",)),
    )
    files = object()
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        "panopticon.engine.scan_adapters.discover_config", lambda root, path: config
    )
    monkeypatch.setattr(
        "panopticon.engine.scan_adapters.collect_static_files",
        lambda root, ignored: calls.update(root=root, ignored=ignored) or files,
    )
    monkeypatch.setattr(
        "panopticon.engine.scan_adapters.select_rule_ids",
        lambda selected: calls.update(selected=selected) or selected,
    )
    monkeypatch.setattr(
        "panopticon.engine.scan_adapters.run_semgrep",
        lambda collected, selected, root, *, deadline: (
            calls.update(
                collected=collected, runner_selected=selected, deadline=deadline
            )
            or {
                "SENT-002": [
                    StaticMatch("SENT-002", "z.py", SourceRange(3, 2, 3, 4), "z"),
                    StaticMatch("SENT-002", "a.py", SourceRange(1, 1, 1, 2), "a"),
                ]
            }
        ),
    )

    findings = ProductionSemgrep(Path("configured.toml")).scan(tmp_path)

    assert calls["root"] == tmp_path
    assert calls["ignored"] == ("ignored.py",)
    assert calls["selected"] == ("SENT-002",)
    assert calls["collected"] is files
    assert calls["runner_selected"] == ("SENT-002",)
    assert isinstance(calls["deadline"], float)
    assert [item.path for item in findings] == ["a.py", "z.py"]


def test_scan_request_factory_is_mode_aware_and_preserves_request_options(tmp_path: Path) -> None:
    quick = build_scan_request(
        tmp_path,
        ScanMode.QUICK,
        offline=True,
        cache_available=False,
        config_path=Path("custom.toml"),
    )
    standard = build_scan_request(
        tmp_path, ScanMode.STANDARD, config_path=Path("custom.toml")
    )
    deep = build_scan_request(tmp_path, ScanMode.DEEP)

    assert quick.semgrep is None and quick.advisory is None
    assert quick.offline and not quick.cache_available
    assert quick.config_path == Path("custom.toml")
    assert standard.semgrep is not None and standard.advisory is not None
    assert standard.config_path == Path("custom.toml")
    assert deep.semgrep is not None and deep.advisory is not None
    assert deep.semantic is None and deep.dynamic_self is None
