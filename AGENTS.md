# AGENTS.md — Panopticon

> This file is the single source of instructions for any coding agent (Claude Code, Codex, Cursor, Gemini CLI, etc.) working in this repository. `CLAUDE.md` imports this file; do not duplicate content there.

## What this project is

**Panopticon** (`pano`) is a local-first MCP behavior observatory.

> We don't watch you. We watch your MCPs.

It discovers MCP servers installed in AI clients, runs them inside a decoy-filled sandbox, records what they actually do (files, network, processes, leaks) per tool call, and compares observed behavior against what the server *declares*. It also fixes risky configs, wraps servers for continuous recording, and (for MCP authors) runs static/semantic/dependency analysis vendored from the upstream project `BashaarJavaid/MCP-Sentinel` at pinned commit `e717e955` (MIT).

The complete product and implementation plan is in **`panopticon-buildplan.md`**. Read it before starting any epic. This file tells you *how to work*; `panopticon-buildplan.md` tells you *what to build*; `ARCHITECTURE.md` and `docs/DECISIONS.md` hold the frozen contracts you may not renegotiate on your own.

## Ground rules (non-negotiable)

1. **Observation before judgment.** Reports say what a server *did*. They never say "safe" or "dangerous" as a verdict. Forbidden words in user-facing text: `safe`, `certified`, `dangerous` (as a verdict), `perfect`, `100%`. A numeric safety score is separately prohibited. The machine-checked phrase list lives in `src/panopticon/i18n/glossary.yaml` and the i18n linter enforces it (DECISIONS #15).
2. **Unknown is visible.** Anything not observed, unsupported, skipped, or timed out is reported as `UNKNOWN`/`INCOMPLETE`/`UNSUPPORTED`. Never collapse it into a pass. Stage results carry an exhaustive status, a stable `reason_code`, and explicit coverage dimensions (DECISIONS #8); a bare stage string is not acceptable.
3. **The user's home never enters a container.** No bind mounts of `$HOME` or project directories, except the explicit `--self` read-only source mount. Decoy home only.
4. **Every persisted artifact passes `util.leak_check`** before it is written: no real token values, no real home absolute paths, no `--real-env` values, no plaintext Panopticon-managed secret material. This applies to observations, baselines, wrap logs, logs, PNGs, SARIF. `store/` is the only writer (DECISIONS #9); the fix/install config patcher is the one narrow exception and follows the same journal, backup, and leak rules.
5. **Determinism.** Same input → same output. `diff` on identical observations must be zero. Canonicalize before comparing (sort, strip timestamps/PIDs/durations/container IDs), and compare run metadata separately from the semantic view.
6. **Fix is always: dry-run diff → confirm → backup → apply → re-check → undo available.** Never edit a client config outside `fix/` and `install/` code paths. Secret-bearing fixes go through `SecretStore`; with no secure backend they are guidance-only (DECISIONS #10).
7. **ko and en are the same rule.** Every rule has `i18n/ko/rules/<ID>.md` and `i18n/en/rules/<ID>.md` with identical 6-section structure. CI fails if the ID sets differ.
8. **No telemetry.** Outbound product paths are limited to registry/package-install lookups, the MCP's own traffic inside the sandbox, explicitly permitted remote `watch`, bounded unauthenticated FIX-008 validation, and the user-invoked semantic analyzer in `scan --mode deep` (DECISIONS #12 and #18; exhaustive table: `docs/privacy.md`). `--offline` must disable every path; under `--offline` the semantic result is typed `UNSUPPORTED` and the scan is `INCOMPLETE`.
9. **Don't fork the plan silently.** If an epic's scope, a rule's condition, or a schema must change, edit `panopticon-buildplan.md` in the same PR and say why in the PR body. Contract-level changes also need a `docs/DECISIONS.md` entry.

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
  models/       Branded IDs, immutable persistence-boundary models, stage/status/reason/coverage variants, schema metadata.
  store/        The only writer of persisted artifacts: canonicalize → leak check → atomic replace.
  engine/       Pipeline contracts for doctor/watch/diff/scan; boundary Result and diagnostics.
  secrets/      SecretStore protocol and OS credential-store backends.
  util/         leak_check, paths, canonicalize, jsonc.
schemas/        JSON Schema (2020-12), generated from the runtime models. Development line `0.x`; `1.0` is frozen once at the 0.9 gate (§21, §23).
panopticon-buildplan.md   The plan (what to build). ARCHITECTURE.md, ROADMAP.md at root.
action.yml      GitHub Action wrapper around `pano ci`. panopticon.toml: example project config for the analyze line.
THIRD_PARTY_NOTICES.md    Upstream MIT attribution; list every vendored file here.
tests/          unit/, integration/ (Docker-marked), e2e/, fixtures/.
docs/           DECISIONS.md (frozen contracts), PROGRESS.md, limitations.md, privacy.md, disclosure.md, self-declaration.md, contributing.md, README.ko.md, rules/.
scripts/        Dev helpers (image build, i18n check, rule catalog generation).
```

Dependency direction: `cli → engine → *`, `analyzers → findings, rules`, `probe → sandbox`, `diff → baseline, findings`, `reporters` read the sanitized render model only. `store` is imported by everything that persists and imports no feature package. `sandbox` and `wrap` do not import each other. Full contract: `ARCHITECTURE.md`.

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
- Work epic by epic in the dependency order in `panopticon-buildplan.md §3`. Do not start an epic whose dependencies are not closed.
- An epic is **closed** only when every item in its "Definition of done" passes in CI. Proof comes from a rerun gate, never from a summary claiming green.
- Track progress in `docs/PROGRESS.md` (one line per epic: `E05 — IN PROGRESS — <what remains>`). Update it in every PR that touches the epic.
- Parallel work uses task-owned branches `feature/eNN-<slice>` in worktrees under `~/.config/superpowers/worktrees/panopticon/`. The root worktree is integration-only `main`. Never edit another active worker's owned paths; return a shared-edit manifest instead and let the integrator apply it after the owning commit lands.
- Shared integration files (`pyproject.toml`, `uv.lock`, `schemas/`, CLI registration, the buildplan, `docs/PROGRESS.md`, rule and i18n manifests, CI and release workflows) belong to the integrator unless a task explicitly owns them.

### Adding a rule
1. Implement in `analyzers/<line>/rules.py` with the `@rule(...)` decorator (`rules/registry.py`).
2. Add `tests/fixtures/...` positive **and** negative cases; `scripts/check_rules.py` fails otherwise.
3. Add `i18n/en/rules/<ID>.md` and `i18n/ko/rules/<ID>.md` using `i18n/RULE_TEMPLATE.md` (6 sections: Problem / Impact / Evidence / Recommended action / How to verify / Limits).
4. Add the row to `panopticon-buildplan.md §20`.

### Adding a client adapter
1. `discovery/<client>.py` implementing `ClientAdapter` (`discovery/base.py`).
2. Fixtures under `tests/fixtures/discovery/<client>/` — at minimum: `clean.json`, `secret.json`, `broad_fs.json`, `duplicate.json`, `malformed.json`, `disabled.json`, `remote.json`.
3. Register in `discovery/__init__.py`. Add the row to `panopticon-buildplan.md §5`.

### Schemas
- Persisted schemas live on the `0.x` development line. Any change to a persisted shape → regenerate `schemas/*.json` from the runtime models, bump `schema_version` within 0.x if breaking, add an explicitly dispatched idempotent migrator in `baseline/migrate.py`, update `panopticon-buildplan.md §21`.
- Do not write `1.0` into a schema before the 0.9 release-candidate gate. That freeze happens exactly once (DECISIONS #6).
- Round-trip tests in `tests/unit/test_schema_roundtrip.py` must pass, and migration replay must converge idempotently from every shipped 0.x version.

### Identity
- `server_id` groups; `installation_id` addresses one config entry; `logical_key` addresses one finding across runs. Never use one where the contract calls for another (DECISIONS #7, `ARCHITECTURE.md`).

### Upstream code (E16)
- Upstream modules from MCP-Sentinel are vendored from pinned commit `e717e955` into `analyzers/static`, `analyzers/semantic`, `analyzers/dependency`. Preserve the MIT copyright header in each copied file, record it in the per-file provenance and checksum manifest, and list it in `THIRD_PARTY_NOTICES.md`. Keep the 125 upstream tests under `tests/upstream/` green; a failing upstream test is stabilization work, never a deletion or a skip.
- The repository does not claim upstream Git ancestry. Provenance is the pinned commit plus per-file hashes (DECISIONS #13).
- You may clone `https://github.com/BashaarJavaid/MCP-Sentinel` into a disposable directory **outside** the repository and read it when you need upstream business logic in context (DECISIONS #13a). Do not modify that clone, do not vendor from a moving branch, and do not import its Git history. Everything you vendor still comes from `e717e955` and lands in the checksum manifest with its enumerated test IDs. Delete the clone when E16 vendoring is done and prove the path is gone.

## Code standards

- Python 3.11+, `uv`, `ruff` (line length 100), `mypy --strict` on `src/`.
- No source module over 250 pure lines of code. No wildcard imports, no `shell=True`, no untyped boundary dictionaries, no suppression comments, no broad exception swallowing.
- New dependencies are allowed only when the accepted buildplan requires them, and only after official-document verification, license compatibility review, known-vulnerability screening, a lockfile update, and a green affected gate. Removing a dependency needs approval.
- Coverage gate (`fail_under` in `pyproject.toml`) starts at 40 for the scaffold and is raised in every epic-closing PR toward the 85 target. Never lower it.
- Never run `ruff --unsafe-fixes` blindly: T20 will delete `print` calls (scripts/ and reporters/ are exempted).
- Typed everywhere. `Protocol` for boundaries (`Runtime`, `ClientAdapter`, `Extractor`, `Reporter`).
- No logic in `cli/`. No `print` outside `reporters/`.
- Errors are values at boundaries: collectors return `Result` with an exhaustive state (`COMPLETE | PARTIAL | INCOMPLETE | FAILED | UNSUPPORTED | SKIPPED | NOT_REQUESTED`) plus a stable `reason_code`, never raise across an epic boundary.
- CLI exit codes are one table with a defined precedence covering success, policy findings, incomplete required stages, runtime errors, config errors, and usage errors. `cli/` renders states; it never reinterprets them.
- Paths in persisted data are `~`-relative. Hosts lowercase. Times UTC ISO-8601.
- Subprocesses: `asyncio.create_subprocess_exec`, never `shell=True`.
- Logging via `structlog`; log records pass `leak_check` too.

## Testing standards

- Every module has unit tests. Docker-dependent tests are marked `@pytest.mark.docker` and run in a separate CI job.
- Fixture MCP servers live in `tests/fixtures/mcp/{evil,clean}/` and are real, runnable stdio servers (Node and Python). `evil/*` each exhibit exactly one behavior class (file read, host connect, decoy leak, idle beacon, process exec). `clean/*` must yield zero `confirmed` findings.
- Determinism test: run twice, diff must be empty — for observations, baselines, and every reporter output.
- Leak tests: `tests/fixtures/leak/` contains 20+ payloads across raw, escaped, URL-encoded, form-encoded, base64, and chunk-split variants plus native and WSL home paths; every persist sink must reject them.
- No fixed sleeps and no polling loops in tests. Subscribe to the exact event or state change, then await it with a bounded timeout.
- Do not test prose wording. Test IDs, section structure, lookup and fallback behavior, and equality of generated copy.

## Things you must not do

- Do not add `--upload`, crash reporting, analytics, update pings, or any outbound call outside the exhaustive `docs/privacy.md` table and DECISIONS #18.
- Do not add telemetry, hosted accounts, a dashboard, a public observatory or catalog, a numeric safety score, a certification verdict, a native Windows sandbox, or any post-1.0 roadmap item.
- Do not mount the user's home or cwd into a container (except `--self`, read-only).
- Do not write "Safe", "Certified", or a numeric safety score anywhere.
- Do not write persisted artifacts outside `store/` and the approved config-patch modules.
- Do not write a plaintext secret file, an unencrypted secret-bearing backup, or a raw registry or trace payload to disk.
- Do not delete or add MCP entries in a client config. `fix` edits values; `install` swaps `command`/`args` and preserves the original under `_pano_original`.
- Do not skip `panopticon-buildplan.md` updates when behavior changes.
- Do not weaken a "Definition of done" to close an epic.

## Where to ask

Open questions go to `docs/DECISIONS.md` as a numbered entry (context, options, chosen, why). Undecided items from `panopticon-buildplan.md §24` live there too.
