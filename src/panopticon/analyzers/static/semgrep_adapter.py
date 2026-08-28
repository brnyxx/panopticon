# Copyright (c) 2026 MCP Sentinel contributors
# SPDX-License-Identifier: MIT
"""Pinned Semgrep CLI adapter for generic static pattern rules."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import certifi

from panopticon.analyzers.static.model import SourceRange, StaticFileSet, StaticMatch

SEMGREP_VERSION = "1.170.0"
SEMGREP_BATCH_SIZE = 200
SEMGREP_TIMEOUT_SECONDS = 10


class SemgrepExecutionError(RuntimeError):
    """Explicit, non-persistent Semgrep infrastructure failure."""


def run_semgrep(
    files: StaticFileSet, selected_rule_ids: tuple[str, ...], scan_root: Path, *, deadline: float
) -> dict[str, list[StaticMatch]]:
    rule_ids = tuple(
        rule_id for rule_id in selected_rule_ids if rule_id in {"SENT-002", "SENT-005"}
    )
    results = {rule_id: [] for rule_id in rule_ids}
    if not rule_ids:
        return results
    _verify_version()
    executable = shutil.which("semgrep") or str(Path(sys.executable).with_name("semgrep"))
    if not Path(executable).is_file():
        raise SemgrepExecutionError("Semgrep executable is not available")
    paths = sorted(
        (*(item.path for item in files.python_files), *files.config_files),
        key=lambda path: path.as_posix(),
    )
    if not paths:
        return results
    configs = [
        Path(__file__).parent / "semgrep" / f"{rid.lower().replace('-', '')}.yaml"
        for rid in rule_ids
    ]
    return asyncio.run(
        _run_batches(executable, configs, paths, files, results, scan_root, deadline)
    )


async def _run_batches(
    executable: str,
    configs: Sequence[Path],
    paths: Sequence[Path],
    files: StaticFileSet,
    results: dict[str, list[StaticMatch]],
    scan_root: Path,
    deadline: float,
) -> dict[str, list[StaticMatch]]:
    env = os.environ.copy()
    env.update(
        {
            "SEMGREP_SEND_METRICS": "off",
            "SEMGREP_ENABLE_VERSION_CHECK": "0",
            "SSL_CERT_FILE": certifi.where(),
        }
    )
    for index in range(0, len(paths), SEMGREP_BATCH_SIZE):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SemgrepExecutionError("static analysis exceeded its timeout")
        with tempfile.TemporaryDirectory(prefix="panopticon-semgrep-") as directory:
            output = Path(directory) / "results.json"
            env.update(
                {
                    "SEMGREP_LOG_FILE": str(Path(directory) / "semgrep.log"),
                    "SEMGREP_SETTINGS_FILE": str(Path(directory) / "settings.yml"),
                }
            )
            command = [
                executable,
                "scan",
                "--json",
                "--output",
                str(output),
                "--jobs",
                "1",
                "--timeout",
                str(SEMGREP_TIMEOUT_SECONDS),
                "--metrics",
                "off",
                "--disable-version-check",
                "--disable-nosem",
            ]
            for config in configs:
                command.extend(("--config", str(config)))
            command.extend(str(path) for path in paths[index : index + SEMGREP_BATCH_SIZE])
            try:
                proc = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        *command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=env,
                    ),
                    timeout=min(SEMGREP_TIMEOUT_SECONDS, remaining),
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=min(SEMGREP_TIMEOUT_SECONDS, remaining)
                )
            except (TimeoutError, OSError) as error:
                raise SemgrepExecutionError(f"Semgrep execution failed: {error}") from error
            if proc.returncode not in {0, 1}:
                raise SemgrepExecutionError(
                    f"Semgrep execution failed: {stderr.decode(errors='replace').strip() or 'unknown failure'}"
                )
            if not output.is_file():
                raise SemgrepExecutionError("Semgrep wrote no JSON report")
            _collect(_parse(output.read_text(encoding="utf-8")), results, files, scan_root)
    return results


def _verify_version() -> None:
    try:
        installed = version("semgrep")
    except PackageNotFoundError as error:
        raise SemgrepExecutionError("Semgrep 1.170.0 is not installed") from error
    if installed != SEMGREP_VERSION:
        raise SemgrepExecutionError(
            f"Semgrep version mismatch: expected {SEMGREP_VERSION}, found {installed}"
        )


def _parse(raw: str) -> Mapping[str, object]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SemgrepExecutionError("Semgrep returned invalid JSON") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise SemgrepExecutionError("Semgrep returned an unexpected JSON shape")
    if payload.get("errors"):
        raise SemgrepExecutionError("Semgrep reported scan errors")
    return payload


def _collect(
    payload: Mapping[str, object],
    results: dict[str, list[StaticMatch]],
    files: StaticFileSet,
    scan_root: Path,
) -> None:
    entries = payload["results"]
    if not isinstance(entries, list):
        raise SemgrepExecutionError("Semgrep returned invalid results")
    for item in entries:
        if not isinstance(item, dict):
            raise SemgrepExecutionError("Semgrep result entry is not an object")
        extra = item.get("extra", {})
        metadata = extra.get("metadata", {}) if isinstance(extra, dict) else {}
        rule_id = metadata.get("sentinel_rule_id") if isinstance(metadata, dict) else None
        if not isinstance(rule_id, str) or rule_id not in results:
            continue
        try:
            start, end = item["start"], item["end"]
            start_line, start_col = int(start["line"]), int(start["col"])
            end_col = max(int(end["col"]), start_col + 1)
            relative = _relative(Path(str(item.get("path", ""))).resolve(), files, scan_root)
        except (KeyError, TypeError, ValueError) as error:
            raise SemgrepExecutionError("Semgrep returned an invalid source range") from error
        snippet = str(extra.get("lines", "")) if isinstance(extra, dict) else ""
        results[rule_id].append(
            StaticMatch(
                rule_id=rule_id,
                path=relative,
                range=SourceRange(
                    start_line=start_line,
                    start_column=start_col,
                    end_line=int(end["line"]),
                    end_column=end_col,
                ),
                snippet=snippet,
                match_kinds=(str(item.get("check_id", "semgrep")),),
            )
        )


def _relative(path: Path, files: StaticFileSet, scan_root: Path) -> str:
    for item in files.python_files:
        if item.path == path:
            return item.relative_path
    for item in files.config_files:
        if item == path:
            return path.relative_to(scan_root).as_posix()
    raise SemgrepExecutionError(f"Semgrep returned an out-of-scope path: {path}")
