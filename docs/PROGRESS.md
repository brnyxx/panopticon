# Progress

One line per epic. Update in every PR touching the epic. States: TODO / IN PROGRESS / BLOCKED / CLOSED.

An epic is CLOSED only when every item in its definition of done has been proven by a rerun gate, with an evidence link. A summary claiming green is not proof.

| Epic | State | Remaining |
|---|---|---|
| E01 Foundation | CLOSED | typed persisted contracts, schema lifecycle, canonical leak-checked `store/` gateway, direct-write checker, credential-backed `SecretStore`/encrypted backups, engine pipelines, and the exit-code table are complete |
| E02 Discovery | CLOSED | six adapters, the 48-file fixture matrix, isolated-home doctor CLI, partial-adapter preservation, and deterministic terminal/JSON grouping pass |
| E03 Inventory | CLOSED | normalization, stable installation identity, cache version lookup, command fixtures, duplicate grouping, and doctor integration pass |
| E04 Registry | IN PROGRESS | normalized npm/PyPI/GitHub history, offline/ETag snapshots, typed wire failures, transitions, HIST rules, and doctor context pass; default live/cache provider wiring remains |
| E05 Sandbox | IN PROGRESS | Docker and rootless Podman runtime/isolation/proxy/DNS tests pass; release image digests and platform matrix remain |
| E06 Decoy | IN PROGRESS | complete synthetic home/environment matrix, canonical archive, project filename replication, bounded variant matching, typed watch materialization, and the real single-behavior fixture matrix pass; container leak-class acceptance remains |
| E07 Events | IN PROGRESS | stateful strace/netlog parsers, source-specific coverage, deterministic span attribution, watch collection seams, and real behavior fixtures pass; exact end-to-end event attribution sets remain |
| E08 Probe | IN PROGRESS | dual-era client, modern 2026-07-28 plus legacy fallback, schema solver, deterministic call driver, local/remote watch orchestration, and Python/Node fixture protocol runs pass; five official-example call runs remain |
| E09 Remote | CLOSED | bounded Streamable HTTP/JSON/SSE/legacy/session flows, SSRF/redirect policy, decoy matching, credential stripping, and explicit remote coverage pass |
| E10 Declared | CLOSED | six-source extraction, explicit completeness authority, tool isolation, host/path/process normalization, and labeled-corpus tests pass |
| E11 Findings/Rules | IN PROGRESS | typed finding construction, logical/occurrence keys, source states, suppressions, and rule failure diagnostics pass; rule sets remain |
| E12 Rules | IN PROGRESS | CFG-001..012, HIST-001..004, and WATCH-001..014 are registered with exact fixtures and ko/en docs; exact evil/clean end-to-end finding sets remain |
| E13 Fix | IN PROGRESS | all six FIX plans, encrypted secret backup, guidance-only fallback, six-client disabled-entry apply/re-check/undo, comment preservation, and concurrent-edit rejection pass; every fix across every client fixture remains |
| E14 Baseline/Diff | CLOSED | leak-checked observation/baseline repository, create/list/show/rm CLI, 0.x migration replay, deterministic semantic views, and coverage-aware deltas pass |
| E15 Wrap/Install | IN PROGRESS | byte-transparent relay, framing isolation, cancellation/signals, child exit propagation, immutable per-installation records, UTC retention, CLI, and latency gate pass; native event monitoring, alerts, install/uninstall, and five official-example manual proof remain |
| E16 Analyze line | IN PROGRESS | exact pinned replay (125 tests), adapted static/semantic/dependency modules, provenance verifier, and notices pass; full scan orchestration remains |
| E17 Reporters | IN PROGRESS | terminal, JSON, SARIF, Markdown, deterministic ko/en PNG, accessible badge, leak rejection, store persistence, and stable hashes pass; live GitHub SARIF upload proof remains |
| E18 i18n | IN PROGRESS | WATCH-001 plus all 16 CFG/HIST documents pass bilingual structure and glossary gates; remaining WATCH/FIX/SENT documents and explain remain |
| E19 Release | TODO | scope in §28; targets are `brnyxx/panopticon`, `ghcr.io/brnyxx`, PyPI `panopticon-mcp`, `brnyxx/homebrew-tap` |

## Why E01 is closed

The scaffold builds, CI is green, and the contracts above are now frozen in writing. The typed spine, persistence gateway, credential-backed secret storage, engine boundaries, and exit-code policy are complete; the combined Task5 + Task6 acceptance gates pass.
