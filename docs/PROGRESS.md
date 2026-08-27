# Progress

One line per epic. Update in every PR touching the epic. States: TODO / IN PROGRESS / BLOCKED / CLOSED.

An epic is CLOSED only when every item in its definition of done has been proven by a rerun gate, with an evidence link. A summary claiming green is not proof.

| Epic | State | Remaining |
|---|---|---|
| E01 Foundation | IN PROGRESS | contracts frozen (docs/DECISIONS.md #6-#12, ARCHITECTURE.md); still open: typed models and branded IDs, `installation_id`, structured stage/reason/coverage, 0.1 schemas and migrators, the `store/` gateway and direct-write checker, `SecretStore` backends, engine pipelines and the exit-code table |
| E02 Discovery | TODO | |
| E03 Inventory | TODO | needs `installation_id` from E01 |
| E04 Registry | TODO | |
| E05 Sandbox | TODO | image namespace decided: `ghcr.io/brnyxx` (DECISIONS #1) |
| E06 Decoy | TODO | |
| E07 Events | TODO | |
| E08 Probe | TODO | dual-era client, modern 2026-07-28 plus legacy fallback (DECISIONS #11) |
| E09 Remote | TODO | |
| E10 Declared | TODO | |
| E11 Findings/Rules | TODO | registry stub exists; needs `logical_key` separate from the occurrence id |
| E12 Rules | TODO | 30 observe rules (§20.6); WATCH-001 docs exist as the template example |
| E13 Fix | TODO | secret-bearing fixes go through `SecretStore`, guidance-only fallback (DECISIONS #10) |
| E14 Baseline/Diff | TODO | |
| E15 Wrap/Install | TODO | |
| E16 Analyze line | TODO | vendor from pinned `e717e955` with headers, per-file checksums, enumerated test IDs → THIRD_PARTY_NOTICES.md |
| E17 Reporters | TODO | scope in §26; terminal-style evidence card decided (DECISIONS #5) |
| E18 i18n | TODO | scope in §27; 47 rule documents in ko and en (§20.6) |
| E19 Release | TODO | scope in §28; targets are `brnyxx/panopticon`, `ghcr.io/brnyxx`, PyPI `panopticon-mcp`, `brnyxx/homebrew-tap` |

## Why E01 is still open

The scaffold builds, CI is green, and the contracts above are now frozen in writing. None of that closes E01: its definition of done requires the typed spine, the persistence gateway, the secret backends, and the engine boundaries to exist and pass their gates. Freezing a contract is not implementing it.
