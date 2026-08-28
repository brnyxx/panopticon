# Progress

One line per epic. Update in every PR touching the epic. States: TODO / IN PROGRESS / BLOCKED / CLOSED.

An epic is CLOSED only when every item in its definition of done has been proven by a rerun gate, with an evidence link. A summary claiming green is not proof.

| Epic | State | Remaining |
|---|---|---|
| E01 Foundation | CLOSED | typed persisted contracts, schema lifecycle, canonical leak-checked `store/` gateway, direct-write checker, credential-backed `SecretStore`/encrypted backups, engine pipelines, and the exit-code table are complete |
| E02 Discovery | IN PROGRESS | six adapters and the 48-file fixture matrix pass; doctor rendering closes in Task 24 |
| E03 Inventory | IN PROGRESS | normalization, stable installation identity, cache version lookup, and 30 command fixtures pass; doctor integration closes in Task 24 |
| E04 Registry | TODO | |
| E05 Sandbox | IN PROGRESS | Docker and rootless Podman runtime/isolation/proxy/DNS tests pass; release image digests and platform matrix remain |
| E06 Decoy | TODO | |
| E07 Events | TODO | |
| E08 Probe | TODO | dual-era client, modern 2026-07-28 plus legacy fallback (DECISIONS #11) |
| E09 Remote | TODO | |
| E10 Declared | TODO | |
| E11 Findings/Rules | IN PROGRESS | typed finding construction, logical/occurrence keys, source states, suppressions, and rule failure diagnostics pass; rule sets remain |
| E12 Rules | TODO | 30 observe rules (§20.6); WATCH-001 docs exist as the template example |
| E13 Fix | TODO | secret-bearing fixes go through `SecretStore`, guidance-only fallback (DECISIONS #10) |
| E14 Baseline/Diff | TODO | |
| E15 Wrap/Install | TODO | |
| E16 Analyze line | TODO | vendor from pinned `e717e955` with headers, per-file checksums, enumerated test IDs → THIRD_PARTY_NOTICES.md |
| E17 Reporters | TODO | scope in §26; terminal-style evidence card decided (DECISIONS #5) |
| E18 i18n | TODO | scope in §27; 47 rule documents in ko and en (§20.6) |
| E19 Release | TODO | scope in §28; targets are `brnyxx/panopticon`, `ghcr.io/brnyxx`, PyPI `panopticon-mcp`, `brnyxx/homebrew-tap` |

## Why E01 is closed

The scaffold builds, CI is green, and the contracts above are now frozen in writing. The typed spine, persistence gateway, credential-backed secret storage, engine boundaries, and exit-code policy are complete; the combined Task5 + Task6 acceptance gates pass.
