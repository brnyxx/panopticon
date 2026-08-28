# Progress

One line per epic. Update in every PR touching the epic. States: TODO / IN PROGRESS / BLOCKED / CLOSED.

An epic is CLOSED only when every item in its definition of done has been proven by a rerun gate, with an evidence link. A summary claiming green is not proof.

| Epic | State | Remaining |
|---|---|---|
| E01 Foundation | CLOSED | typed persisted contracts, schema lifecycle, canonical leak-checked `store/` gateway, direct-write checker, credential-backed `SecretStore`/encrypted backups, engine pipelines, and the exit-code table are complete |
| E02 Discovery | IN PROGRESS | six adapters and the 48-file fixture matrix pass; doctor rendering closes in Task 24 |
| E03 Inventory | IN PROGRESS | normalization, stable installation identity, cache version lookup, and 30 command fixtures pass; doctor integration closes in Task 24 |
| E04 Registry | IN PROGRESS | normalized npm/PyPI/GitHub history, offline/ETag snapshots, typed wire failures, and transition tests pass; history rules and doctor integration remain |
| E05 Sandbox | IN PROGRESS | Docker and rootless Podman runtime/isolation/proxy/DNS tests pass; release image digests and platform matrix remain |
| E06 Decoy | IN PROGRESS | complete synthetic home/environment matrix, canonical archive, project filename replication, and bounded variant matching pass; watch integration remains |
| E07 Events | IN PROGRESS | stateful strace/netlog parsers, source-specific coverage, collector normalization, and deterministic span attribution pass; watch integration remains |
| E08 Probe | IN PROGRESS | dual-era client, modern 2026-07-28 plus legacy fallback, schema solver, destructive-call policy, and deterministic call driver pass; watch integration remains |
| E09 Remote | TODO | |
| E10 Declared | TODO | |
| E11 Findings/Rules | IN PROGRESS | typed finding construction, logical/occurrence keys, source states, suppressions, and rule failure diagnostics pass; rule sets remain |
| E12 Rules | TODO | 30 observe rules (§20.6); WATCH-001 docs exist as the template example |
| E13 Fix | TODO | secret-bearing fixes go through `SecretStore`, guidance-only fallback (DECISIONS #10) |
| E14 Baseline/Diff | TODO | |
| E15 Wrap/Install | TODO | |
| E16 Analyze line | IN PROGRESS | exact pinned replay (125 tests), adapted static/semantic/dependency modules, provenance verifier, and notices pass; full scan orchestration remains |
| E17 Reporters | IN PROGRESS | sanitized render boundary plus deterministic terminal and JSON reporters pass; SARIF/Markdown/PNG remain |
| E18 i18n | TODO | scope in §27; 47 rule documents in ko and en (§20.6) |
| E19 Release | TODO | scope in §28; targets are `brnyxx/panopticon`, `ghcr.io/brnyxx`, PyPI `panopticon-mcp`, `brnyxx/homebrew-tap` |

## Why E01 is closed

The scaffold builds, CI is green, and the contracts above are now frozen in writing. The typed spine, persistence gateway, credential-backed secret storage, engine boundaries, and exit-code policy are complete; the combined Task5 + Task6 acceptance gates pass.
