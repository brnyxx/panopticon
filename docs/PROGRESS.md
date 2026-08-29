# Progress

One line per epic. Update in every PR touching the epic. States: TODO / IN PROGRESS / BLOCKED / CLOSED.

An epic is CLOSED only when every item in its definition of done has been proven by a rerun gate, with an evidence link. A summary claiming green is not proof.

| Epic | State | Remaining |
|---|---|---|
| E01 Foundation | CLOSED | typed persisted contracts, schema lifecycle, canonical leak-checked `store/` gateway, direct-write checker, credential-backed `SecretStore`/encrypted backups, engine pipelines, and the exit-code table are complete |
| E02 Discovery | CLOSED | six adapters, the 48-file fixture matrix, isolated-home doctor CLI, partial-adapter preservation, and deterministic terminal/JSON grouping pass |
| E03 Inventory | CLOSED | normalization, stable installation identity, cache version lookup, command fixtures, duplicate grouping, and doctor integration pass |
| E04 Registry | CLOSED | normalized npm/PyPI/GitHub history, store-backed 24-hour cache, independent GitHub validators, typed offline/wire failures, HIST transitions, and production doctor wiring pass (G013 evidence recorded) |
| E05 Sandbox | CLOSED | Docker and rootless Podman runtime/isolation/proxy/DNS tests, attested six-platform matrix, and verified amd64/arm64 GHCR manifests with immutable lockfile digests pass |
| E06 Decoy | CLOSED | per-run synthetic homes and all encoded, response, file, process, stderr, notification, and network leak sinks pass live container acceptance without persisting marker values |
| E07 Events | CLOSED | stateful trace/network/snapshot/stdout collection, reversible noise filtering, exact call/idle span ownership, skew fallback, and live five-behavior event oracles pass |
| E08 Probe | CLOSED | bounded JSONL and legacy Content-Length decoding, strict dual-era negotiation, schema-generated calls, and all tools on five pinned official implementations pass through the production client/driver |
| E09 Remote | CLOSED | bounded Streamable HTTP/JSON/SSE/legacy/session flows, SSRF/redirect policy, decoy matching, credential stripping, and explicit remote coverage pass |
| E10 Declared | CLOSED | six-source extraction, explicit completeness authority, tool isolation, host/path/process normalization, and labeled-corpus tests pass |
| E11 Findings/Rules | CLOSED | typed finding construction, stable identities, source states, UNKNOWN-visible review findings, suppressions, isolated rule failures, and complete positive/negative registered-rule fixtures pass |
| E12 Rules | CLOSED | CFG-001..012, HIST-001..004, and WATCH-001..014 are registered with bilingual docs, exact evil/clean live finding sets, and relevant event ownership assertions |
| E13 Fix | CLOSED | all six FIX remediations across all six clients pass dry-run, apply, re-check, exact undo, comment preservation, secure-store guidance, and concurrent-edit rejection |
| E14 Baseline/Diff | CLOSED | leak-checked observation/baseline repository, create/list/show/rm CLI, 0.x migration replay, deterministic semantic views, and coverage-aware deltas pass |
| E15 Wrap/Install | CLOSED | byte-transparent cross-platform relay, framing/recorder isolation, cancellation/signals, child exit propagation, portable immutable records, UTC retention, alerts, reversible six-client install/uninstall, and latency gates pass |
| E16 Analyze line | CLOSED | exact pinned replay (125 tests), quick/standard/deep typed orchestration, semantic disclosure before transport/cache, dynamic self analysis, deterministic SARIF/exit policy, provenance, and the hardened self-scan action pass |
| E17 Reporters | CLOSED | terminal, JSON, SARIF, Markdown, deterministic ko/en PNG, accessible SVG badge, leak rejection, store persistence, stable hashes, and live GitHub self-scan SARIF upload pass |
| E18 i18n | CLOSED | all 47 CFG/HIST/WATCH/FIX/SENT documents have matching ko/en six-section structure; locale precedence/fallback, CJK-safe explain, catalog generation, glossary, and phrase gates pass |
| E19 Release | IN PROGRESS | six-platform attested security matrix, ≥85% quality gates, dependency audit, and fail-closed release/performance evidence pass; publication to `ghcr.io/brnyxx`, PyPI `panopticon-mcp`, and `brnyxx/homebrew-tap`, artifact promotion, documentation, and final audits remain |

## Why E01 is closed

The scaffold builds, CI is green, and the contracts above are now frozen in writing. The typed spine, persistence gateway, credential-backed secret storage, engine boundaries, and exit-code policy are complete; the combined Task5 + Task6 acceptance gates pass.
