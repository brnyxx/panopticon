# AGENTS.md — Panopticon

> This file is the single source of instructions for any coding agent (Claude Code, Codex, Cursor, Gemini CLI, etc.) working in this repository. `CLAUDE.md` imports this file; do not duplicate content there.

## What this project is

**Panopticon** (`pano`) is a local-first MCP behavior observatory.

> We don't watch you. We watch your MCPs.

It discovers MCP servers installed in AI clients, runs them inside a decoy-filled sandbox, records what they actually do (files, network, processes, leaks) per tool call, and compares observed behavior against what the server *declares*. It also fixes risky configs, wraps servers for continuous recording, and (for MCP authors) runs static/semantic/dynamic analysis inherited from the upstream project `BashaarJavaid/MCP-Sentinel` (MIT).

The complete product and implementation plan is in **`docs/PLAN.md`**. Read it before starting any epic. This file tells you *how to work*; `docs/PLAN.md` tells you *what to build*.

## Ground rules (non-negotiable)

1. **Observation before judgment.** Reports say what a server *did*. They never say "safe" or "dangerous" as a verdict. Forbidden words in user-facing text: `safe`, `certified`, `dangerous` (as a verdict), `perfect`, `100%`. The i18n linter enforces this.
2. **Unknown is visible.** Anything not observed, unsupported, skipped, or timed out is reported as `UNKNOWN`/`INCOMPLETE`/`UNSUPPORTED`. Never collapse it into a pass.
3. **The user's home never enters a container.** No bind mounts of `$HOME` or project directories, except the explicit `--self` read-only source mount. Decoy home only.
4. **Every persisted artifact passes `util.leak_check`** before it is written: no real token values, no real home absolute paths, no `--real-env` values. This applies to observations, baselines, wrap logs, logs, PNGs, SARIF.
5. **Determinism.** Same input → same output. `diff` on identical observations must be zero. Canonicalize before comparing (sort, strip timestamps/PIDs/durations/container IDs).
6. **Fix is always: dry-run diff → confirm → backup → apply → re-check → undo available.** Never edit a client config outside `fix/` and `install/` code paths.
7. **ko and en are the same rule.** Every rule has `i18n/ko/rules/<ID>.md` and `i18n/en/rules/<ID>.md` with identical 6-section structure. CI fails if the ID sets differ.
8. **No telemetry.** Network use is limited to registry lookups (`registry/`) and the MCP's own traffic inside the sandbox. `--offline` must disable everything.
9. **Don't fork the plan silently.** If an epic's scope, a rule's condition, or a schema must change, edit `docs/PLAN.md` in the same PR and say why in the PR body.

## Repository layout

```
src/panopticon/
  cli/          Typer commands. Parsing and rendering calls only. No logic.
  discovery/    One adapter per client (claude_desktop, claude_code, cursor, vscode, windsurf, generic).
  inventory/    InstalledServer normalization, server_id rules.
  registry/     npm / PyPI / GitHub history lookups with on-disk cache.
  sandbox/      Container runtime abstraction, images, decoy home, tracer (strace), netlog, snapshot.
  probe/        MCP JSON-RPC client, deterministic arg generation, call driver, remote (HTTP/SSE).
  declared/     Extractors for the declared scope (tool descriptions, README, manifests, registry, .panopticon.yaml).
  analyzers/    config/, history/, behavior/ (new) and static/, semantic/, dependency/ (upstream-derived).
  findings/     Finding model, canonical IDs, severity.
  rules/        Rule registry (decorator-based) and rule metadata.
  baseline/     Create/load/canonicalize baselines.
  diff/         Delta computation.
  fix/          FIX-* rules, JSONC round-trip editing, backup journal, undo.
  wrap/         stdio relay, JSON-RPC framing, event recording, alerts.
  reporters/    terminal (rich), json, sarif, markdown, png.
  badge/        SVG badge generation.
  i18n/         Message catalog, rule docs (ko, en), glossary, forbidden-phrase lint.
  util/         leak_check, paths, canonicalize, jsonc.
schemas/        JSON Schema (2020-12), schema_version "1.0".
tests/          unit/, integration/ (Docker-marked), e2e/, fixtures/.
docs/           PLAN.md (the plan), architecture, limitations, privacy, disclosure, self-declaration, rules/.
scripts/        Dev helpers (image build, i18n check, rule catalog generation).
```

Dependency direction: `cli → *`, `analyzers → findings, rules`, `probe → sandbox`, `diff → baseline, findings`, `reporters` read only. `sandbox` and `wrap` do not import each other.

## How to work

### Setup
```bash
uv sync --all-extras
uv run pre-commit install
uv run pano version
```

### Everyday commands
```bash
uv run pytest                      # unit + non-docker integration
uv run pytest -m docker            # needs Docker/Podman
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run python scripts/check_i18n.py
uv run python scripts/check_rules.py   # every registered rule has ≥1 positive and ≥1 negative fixture
make ci                            # everything above
```

### Picking work
- Work epic by epic in the dependency order in `docs/PLAN.md §3`. Do not start an epic whose dependencies are not closed.
- An epic is **closed** only when every item in its "Definition of done" passes in CI.
- Track progress in `docs/PROGRESS.md` (one line per epic: `E05 — IN PROGRESS — <what remains>`). Update it in every PR that touches the epic.

### Adding a rule
1. Implement in `analyzers/<line>/rules.py` with the `@rule(...)` decorator (`rules/registry.py`).
2. Add `tests/fixtures/...` positive **and** negative cases; `scripts/check_rules.py` fails otherwise.
3. Add `i18n/en/rules/<ID>.md` and `i18n/ko/rules/<ID>.md` using `i18n/RULE_TEMPLATE.md` (6 sections: Problem / Impact / Evidence / Recommended action / How to verify / Limits).
4. Add the row to `docs/PLAN.md §20`.

### Adding a client adapter
1. `discovery/<client>.py` implementing `ClientAdapter` (`discovery/base.py`).
2. Fixtures under `tests/fixtures/discovery/<client>/` — at minimum: `clean.json`, `secret.json`, `broad_fs.json`, `duplicate.json`, `malformed.json`, `disabled.json`, `remote.json`.
3. Register in `discovery/__init__.py`. Add the row to `docs/PLAN.md §5`.

### Schemas
- Any change to a persisted shape → update `schemas/*.json`, bump `schema_version` if breaking, add a migrator in `baseline/migrate.py`, update `docs/PLAN.md §21`.
- Round-trip tests in `tests/unit/test_schema_roundtrip.py` must pass.

### Upstream code (E16)
- Upstream modules from MCP-Sentinel are vendored into `analyzers/static`, `analyzers/semantic`, `analyzers/dependency`. Preserve the MIT copyright header in each copied file and list the file in `NOTICE`. Keep upstream tests under `tests/upstream/` green.

## Code standards

- Python 3.11+, `uv`, `ruff` (line length 100), `mypy --strict` on `src/`.
- Coverage gate (`fail_under` in `pyproject.toml`) starts at 40 for the scaffold and is raised in every epic-closing PR toward the 85 target. Never lower it.
- Never run `ruff --unsafe-fixes` blindly: T20 will delete `print` calls (scripts/ and reporters/ are exempted).
- Typed everywhere. `Protocol` for boundaries (`Runtime`, `ClientAdapter`, `Extractor`, `Reporter`).
- No logic in `cli/`. No `print` outside `reporters/`.
- Errors are values at boundaries: collectors return `Result` with a state (`COMPLETE | PARTIAL | INCOMPLETE | FAILED | UNSUPPORTED`), never raise across an epic boundary.
- Paths in persisted data are `~`-relative. Hosts lowercase. Times UTC ISO-8601.
- Subprocesses: `asyncio.create_subprocess_exec`, never `shell=True`.
- Logging via `structlog`; log records pass `leak_check` too.

## Testing standards

- Every module has unit tests. Docker-dependent tests are marked `@pytest.mark.docker` and run in a separate CI job.
- Fixture MCP servers live in `tests/fixtures/mcp/{evil,clean}/` and are real, runnable stdio servers (Node and Python). `evil/*` each exhibit exactly one behavior class (file read, host connect, decoy leak, idle beacon, process exec). `clean/*` must yield zero `confirmed` findings.
- Determinism test: run twice, diff must be empty — for observations, baselines, and every reporter output.
- Leak tests: `tests/fixtures/leak/` contains 20+ payloads; every persist path must reject them.

## Things you must not do

- Do not add `--upload`, crash reporting, analytics, or any outbound call outside `registry/` and the sandbox.
- Do not mount the user's home or cwd into a container (except `--self`, read-only).
- Do not write "Safe", "Certified", or a numeric safety score anywhere.
- Do not delete or add MCP entries in a client config. `fix` edits values; `install` swaps `command`/`args` and preserves the original under `_pano_original`.
- Do not skip `docs/PLAN.md` updates when behavior changes.
- Do not weaken a "Definition of done" to close an epic.

## Where to ask

Open questions go to `docs/DECISIONS.md` as a numbered entry (context, options, chosen, why). Undecided items from `docs/PLAN.md §24` live there too.
