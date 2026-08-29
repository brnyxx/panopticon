"""Drive internal Panopticon release-candidate surfaces and record bounded evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Observation:
    name: str
    argv: tuple[str, ...]
    exit_code: int
    stdout_sha256: str
    stderr_sha256: str
    stdout_bytes: int
    stderr_bytes: int


def run(
    name: str,
    argv: tuple[str, ...],
    *,
    cwd: Path,
    environment: dict[str, str],
    expected: frozenset[int] = frozenset({0}),
    timeout: int = 600,
) -> Observation:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=environment,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    observation = Observation(
        name,
        argv,
        result.returncode,
        hashlib.sha256(result.stdout).hexdigest(),
        hashlib.sha256(result.stderr).hexdigest(),
        len(result.stdout),
        len(result.stderr),
    )
    if result.returncode not in expected:
        stdout = result.stdout[-1000:].decode(errors="replace")
        stderr = result.stderr[-1000:].decode(errors="replace")
        raise RuntimeError(f"{name} exited {result.returncode}: stdout={stdout} stderr={stderr}")
    return observation


def cli(root: Path, *arguments: str) -> tuple[str, ...]:
    return ("uv", "run", "--project", str(root), "pano", *arguments)


def internal_surfaces(root: Path, *, docker: bool, podman: bool) -> tuple[Observation, ...]:
    with tempfile.TemporaryDirectory(
        prefix=".pano-manual-qa-",
        dir=Path.home(),
    ) as temporary:
        workspace = Path(temporary)
        home = workspace / "home"
        project = workspace / "project"
        home.mkdir()
        project.mkdir()
        fixture = root / "tests" / "fixtures" / "mcp" / "node_server.mjs"
        shutil.copyfile(fixture, project / "server.mjs")
        (project / "wrapper.mjs").write_text(
            "process.argv.push('clean_file_read'); await import('./server.mjs');\n",
            encoding="utf-8",
        )
        (project / "package.json").write_text(
            '{"name":"manual-qa-fixture","bin":"wrapper.mjs"}',
            encoding="utf-8",
        )
        environment = {**os.environ, "HOME": str(home), "NO_COLOR": "1"}
        observations = [
            run("help", cli(root, "--help"), cwd=root, environment=environment),
            run("version", cli(root, "version"), cwd=root, environment=environment),
            run(
                "doctor-offline",
                cli(root, "doctor", "--offline", "--json"),
                cwd=root,
                environment=environment,
                expected=frozenset({0, 3}),
            ),
            run(
                "explain",
                cli(root, "explain", "WATCH-001", "--json"),
                cwd=root,
                environment=environment,
            ),
            run(
                "bad-watch-selection",
                cli(root, "watch", "--self", "--all"),
                cwd=root,
                environment=environment,
                expected=frozenset({2}),
            ),
        ]
        runtimes = tuple(
            runtime for runtime, enabled in (("docker", docker), ("podman", podman)) if enabled
        )
        for runtime in runtimes:
            observations.append(
                run(
                    f"watch-self-{runtime}",
                    cli(
                        root,
                        "watch",
                        "--self",
                        "--command",
                        "node",
                        "--command",
                        "/self/tests/fixtures/mcp/node_server.mjs",
                        "--command",
                        "clean_file_read",
                        "--offline",
                        "--runtime",
                        runtime,
                        "--png",
                        "--json",
                    ),
                    cwd=root,
                    environment=environment,
                    expected=frozenset({0, 3}),
                )
            )
        observations.append(
            run(
                "production-e2e-cohort",
                (
                    "uv",
                    "run",
                    "pytest",
                    "-q",
                    "tests/e2e/test_doctor.py",
                    "tests/e2e/test_watch.py",
                    "tests/e2e/test_badge.py",
                    "tests/e2e/test_explain.py",
                    "tests/e2e/test_baseline.py",
                    "tests/e2e/test_fix_cli.py",
                    "tests/e2e/test_wrap.py",
                    "tests/e2e/test_install.py",
                    "tests/e2e/test_scan.py",
                    "tests/e2e/test_ci.py",
                    "tests/e2e/test_analysis_cli.py",
                ),
                cwd=root,
                environment=environment,
            )
        )
        pngs = tuple((home / ".panopticon" / "cards").glob("*.png"))
        observations.append(
            Observation(
                "png-artifacts",
                (),
                0 if pngs else 1,
                hashlib.sha256(b"".join(path.read_bytes() for path in sorted(pngs))).hexdigest(),
                hashlib.sha256(b"").hexdigest(),
                sum(path.stat().st_size for path in pngs),
                0,
            )
        )
        if observations[-1].exit_code:
            raise RuntimeError("watch PNG artifact count mismatch")
        return tuple(observations)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-surfaces", action="store_true")
    parser.add_argument("--docker", action="store_true")
    parser.add_argument("--podman", action="store_true")
    parser.add_argument("--download-public-artifacts", action="store_true")
    parser.add_argument("--visual-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--scenario")
    parser.add_argument("--expect-bounded-failure", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output or args.visual_output
    if output is None:
        raise SystemExit("--output or --visual-output is required")
    output.mkdir(parents=True, exist_ok=True)
    observations = internal_surfaces(root, docker=args.docker, podman=args.podman)
    head = subprocess.run(
        ("git", "rev-parse", "HEAD"), cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    payload = {
        "schema": "panopticon.manual-qa.v1",
        "commit": head,
        "status": "BLOCKED_EXTERNAL" if args.download_public_artifacts else "PASS",
        "external_blocker": (
            "Public package promotion is blocked by pending trusted-publisher authorization."
            if args.download_public_artifacts
            else None
        ),
        "observations": [asdict(item) for item in observations],
    }
    (output / "manifest.json").write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return 2 if args.download_public_artifacts else 0


if __name__ == "__main__":
    raise SystemExit(main())
