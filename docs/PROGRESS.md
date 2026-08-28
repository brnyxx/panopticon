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
| E06 Decoy | IN PROGRESS | complete synthetic home/environment matrix, canonical archive, project filename replication, bounded variant matching, and typed watch materialization pass; real fixture matrix remains |
| E07 Events | IN PROGRESS | stateful strace/netlog parsers, source-specific coverage, deterministic span attribution, and watch collection seams pass; real fixture matrix remains |
| E08 Probe | IN PROGRESS | dual-era client, modern 2026-07-28 plus legacy fallback, schema solver, deterministic call driver, and local/remote watch orchestration pass; real fixture matrix remains |
| E09 Remote | CLOSED | bounded Streamable HTTP/JSON/SSE/legacy/session flows, SSRF/redirect policy, decoy matching, credential stripping, and explicit remote coverage pass |
| E10 Declared | CLOSED | six-source extraction, explicit completeness authority, tool isolation, host/path/process normalization, and labeled-corpus tests pass |
| E11 Findings/Rules | IN PROGRESS | typed finding construction, logical/occurrence keys, source states, suppressions, and rule failure diagnostics pass; rule sets remain |
| E12 Rules | IN PROGRESS | CFG-001..012 and HIST-001..004 are registered with exact fixtures and ko/en docs; WATCH-001..014 remain |
| E13 Fix | TODO | secret-bearing fixes go through `SecretStore`, guidance-only fallback (DECISIONS #10) |
| E14 Baseline/Diff | CLOSED | leak-checked observation/baseline repository, create/list/show/rm CLI, 0.x migration replay, deterministic semantic views, and coverage-aware deltas pass |
| E15 Wrap/Install | TODO | |
| E16 Analyze line | IN PROGRESS | exact pinned replay (125 tests), adapted static/semantic/dependency modules, provenance verifier, and notices pass; full scan orchestration remains |
| E17 Reporters | IN PROGRESS | sanitized render boundary plus deterministic terminal and JSON reporters pass; SARIF/Markdown/PNG remain |
| E18 i18n | IN PROGRESS | WATCH-001 plus all 16 CFG/HIST documents pass bilingual structure and glossary gates; remaining WATCH/FIX/SENT documents and explain remain |
| E19 Release | TODO | scope in §28; targets are `brnyxx/panopticon`, `ghcr.io/brnyxx`, PyPI `panopticon-mcp`, `brnyxx/homebrew-tap` |

## Why E01 is closed

The scaffold builds, CI is green, and the contracts above are now frozen in writing. The typed spine, persistence gateway, credential-backed secret storage, engine boundaries, and exit-code policy are complete; the combined Task5 + Task6 acceptance gates pass.
