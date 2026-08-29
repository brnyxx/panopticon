"""Production ports assembled for source scan requests."""

from __future__ import annotations

import time
from pathlib import Path

from panopticon.analyzers.dependency.osv import OsvAdvisory
from panopticon.analyzers.static.engine import STATIC_TIMEOUT_SECONDS, select_rule_ids
from panopticon.analyzers.static.findings import StaticFindingView, finding_views
from panopticon.analyzers.static.model import StaticMatch
from panopticon.analyzers.static.semgrep_adapter import run_semgrep
from panopticon.analyzers.static.traversal import collect_static_files

from .scan import ScanMode, ScanRequest, discover_config


class ProductionSemgrep:
    """Semgrep port composed from the pinned static-analysis primitives."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path

    def scan(self, root: Path) -> tuple[StaticFindingView, ...]:
        config = discover_config(root, self.config_path)
        files = collect_static_files(root, config.scanner.ignore_paths)
        selected = select_rule_ids(config.scanner.selected_rule_ids)
        results = run_semgrep(
            files,
            selected,
            root,
            deadline=time.monotonic() + STATIC_TIMEOUT_SECONDS,
        )
        matches = tuple(
            sorted(
                (match for rule_id in selected for match in results.get(rule_id, ())),
                key=_match_key,
            )
        )
        return finding_views(matches)


def build_scan_request(
    path: Path,
    mode: ScanMode,
    *,
    offline: bool = False,
    cache_available: bool = True,
    config_path: Path | None = None,
) -> ScanRequest:
    """Build a request with required production ports outside quick mode."""
    if mode is ScanMode.QUICK:
        return ScanRequest(
            path=path,
            mode=mode,
            offline=offline,
            cache_available=cache_available,
            config_path=config_path,
        )
    return ScanRequest(
        path=path,
        mode=mode,
        semgrep=ProductionSemgrep(config_path),
        advisory=OsvAdvisory(path.expanduser().resolve()),
        offline=offline,
        cache_available=cache_available,
        config_path=config_path,
    )


def _match_key(match: StaticMatch) -> tuple[str, str, int, int]:
    return (
        match.rule_id,
        match.path,
        match.range.start_line,
        match.range.start_column,
    )


__all__ = ["ProductionSemgrep", "build_scan_request"]
