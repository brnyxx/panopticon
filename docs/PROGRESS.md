# Progress

One line per epic. Update in every PR touching the epic. States: TODO / IN PROGRESS / BLOCKED / CLOSED.

An epic is CLOSED only when every item in its definition of done has been proven by a rerun gate, with an evidence link. A summary claiming green is not proof.

| Epic | State | Remaining |
|---|---|---|
| E01 Foundation | CLOSED | typed persisted contracts, schema lifecycle, canonical leak-checked `store/` gateway, direct-write checker, credential-backed `SecretStore`/encrypted backups, engine pipelines, and the exit-code table pass the exact-product [CI][ci] and final [audit bundle][audit] |
| E02 Discovery | CLOSED | six adapters, the 48-file fixture matrix, isolated-home doctor CLI, partial-adapter preservation, and deterministic terminal/JSON grouping pass the exact-product [CI][ci] and final [audit bundle][audit] |
| E03 Inventory | CLOSED | normalization, stable installation identity, cache version lookup, command fixtures, duplicate grouping, and doctor integration pass the exact-product [CI][ci] and final [audit bundle][audit] |
| E04 Registry | CLOSED | normalized npm/PyPI/GitHub history, store-backed 24-hour cache, independent GitHub validators, typed offline/wire failures, HIST transitions, and production doctor wiring pass the exact-product [CI][ci] and final [audit bundle][audit] |
| E05 Sandbox | CLOSED | Docker and rootless Podman isolation/proxy/DNS tests, the attested six-platform [matrix][platform], and the public locked GHCR digests in [recovery attempt 2][promotion] pass |
| E06 Decoy | CLOSED | per-run synthetic homes and all encoded, response, file, process, stderr, notification, and network leak sinks pass live container acceptance in exact-product [CI][ci] and the [G014 audit evidence][audit] |
| E07 Events | CLOSED | stateful trace/network/snapshot/stdout collection, reversible noise filtering, exact call/idle span ownership, skew fallback, and live five-behavior event oracles pass exact-product [CI][ci] and the [G014 audit evidence][audit] |
| E08 Probe | CLOSED | bounded dual framing/negotiation, schema-generated calls, and all 56 tools on five pinned official implementations pass exact-product [CI][ci], the [source release run][source], and [G014 audit evidence][audit] |
| E09 Remote | CLOSED | bounded HTTP/SSE/session flows, SSRF/redirect policy, decoy matching, credential stripping, and explicit coverage pass exact-product [CI][ci] and the final [audit bundle][audit] |
| E10 Declared | CLOSED | six-source extraction, completeness authority, tool isolation, normalization, and labeled-corpus behavior pass exact-product [CI][ci] and the final [audit bundle][audit] |
| E11 Findings/Rules | CLOSED | typed findings, stable identities, UNKNOWN-visible review findings, suppressions, isolated failures, and complete rule fixtures pass exact-product [CI][ci] and [G014 audit evidence][audit] |
| E12 Rules | CLOSED | CFG-001..012, HIST-001..004, and WATCH-001..014, bilingual docs, exact evil/clean findings, and ownership assertions pass exact-product [CI][ci] and [G014 audit evidence][audit] |
| E13 Fix | CLOSED | all six remediations across all six clients pass dry-run, apply, originating-rule re-check, exact undo, preservation, secure-store guidance, and conflict rejection in exact-product [CI][ci] and [G014 audit evidence][audit] |
| E14 Baseline/Diff | CLOSED | leak-checked repositories, full CLI, 0.x replay, deterministic semantic views, and coverage-aware deltas pass exact-product [CI][ci] and the final [audit bundle][audit] |
| E15 Wrap/Install | CLOSED | byte-transparent relay, portable immutable records, retention/alerts, reversible six-client install/uninstall, and latency gates pass exact-product [CI][ci] and the six-platform [matrix][platform] |
| E16 Analyze line | CLOSED | exact 125-test replay, typed scan modes, semantic disclosure, dynamic self analysis, deterministic SARIF/exit policy, provenance, and hardened self-scan pass exact-product [CI][ci] and the final [audit bundle][audit] |
| E17 Reporters | CLOSED | terminal, JSON, SARIF, Markdown, deterministic ko/en PNG, accessible SVG, leak rejection, persistence, stable hashes, and live self-scan upload pass exact-product [CI][ci] and the final [audit bundle][audit] |
| E18 i18n | CLOSED | all 47 bilingual six-section rule documents, locale precedence/fallback, CJK-safe explain, catalog generation, glossary, and phrase gates pass exact-product [CI][ci] and the final [audit bundle][audit] |
| E19 Release | CLOSED | v1.0.0 remains immutable; exact commit `1f92491` passes [patch CI][patch-ci] and the [six-platform matrix][patch-platform], [rehearsal][patch-source] built once, [promotion][patch-promotion] published the unchanged PyPI and 28-asset [v1.0.1 release][patch-release] while reusing public `ghcr.io/brnyxx` digests, and public uvx, pipx, native archive, and [Homebrew tap][patch-homebrew] installs pass |
| E20 npm & hardening | CLOSED | exact commit `902c0e7` was built once by the signed [1.0.2 rehearsal][e20-rehearsal]; the final usability tree passes [CI][e20-ci] and the [six-platform matrix][e20-platform], [production][e20-promotion] promoted the retained PyPI/npm bytes and 48-asset [v1.0.2 release][e20-release], the exact formula is public in the [Homebrew tap][e20-homebrew], and no-cache uvx, isolated npm, native archive, and Homebrew install/version checks pass; bilingual CLI guidance, Fable-5-reviewed Pages, explicit offline image staging, protected promotion, reproducible Python builds, authoritative cleanup, and registry propagation gates are closed |

Public verification on 2026-08-31: `uvx --no-cache --from 'panopticon-mcp==1.0.2' pano
version`, an isolated `npm install @brnyxx/panopticon@1.0.2`, the checksum-verified Darwin arm64
archive, and `brew test brnyxx/tap/panopticon` each returned `pano 1.0.2 (schema 1.0)`.
All 24 public Sigstore bundles verify offline against the exact `release.yml@refs/heads/main`
identity. The final tree also passes `make ci`: 1,634 passed, one skipped, 32 deselected, and
85.43% coverage.

[ci]: https://github.com/brnyxx/panopticon/actions/runs/33226587357
[platform]: https://github.com/brnyxx/panopticon/actions/runs/33226587338/attempts/2
[audit]: https://github.com/brnyxx/panopticon/blob/4900605/audit-evidence/manifest.json
[source]: https://github.com/brnyxx/panopticon/actions/runs/33242971985
[promotion]: https://github.com/brnyxx/panopticon/actions/runs/33252756023/attempts/2
[release]: https://github.com/brnyxx/panopticon/releases/tag/v1.0.0
[homebrew]: https://github.com/brnyxx/homebrew-tap/commit/61541be837d9df9a895bcde69e42b7ac4ec50444
[patch-ci]: https://github.com/brnyxx/panopticon/actions/runs/33257641232
[patch-platform]: https://github.com/brnyxx/panopticon/actions/runs/33257641129
[patch-source]: https://github.com/brnyxx/panopticon/actions/runs/33257963233/attempts/2
[patch-promotion]: https://github.com/brnyxx/panopticon/actions/runs/33258298469/attempts/2
[patch-release]: https://github.com/brnyxx/panopticon/releases/tag/v1.0.1
[patch-homebrew]: https://github.com/brnyxx/homebrew-tap/commit/7733d8fec72c6bde2f6b9e284e29ba2c77272eb0
[e20-ci]: https://github.com/brnyxx/panopticon/actions/runs/33382566931
[e20-platform]: https://github.com/brnyxx/panopticon/actions/runs/33382566918
[e20-rehearsal]: https://github.com/brnyxx/panopticon/actions/runs/33356213584/attempts/2
[e20-promotion]: https://github.com/brnyxx/panopticon/actions/runs/33383001430
[e20-release]: https://github.com/brnyxx/panopticon/releases/tag/v1.0.2
[e20-homebrew]: https://github.com/brnyxx/homebrew-tap/commit/c74b28cb03986e69705b82d8b8a89c1e65b7d493

## Why E01 is closed

The scaffold builds, CI is green, and the contracts above are now frozen in writing. The typed spine, persistence gateway, credential-backed secret storage, engine boundaries, and exit-code policy are complete; the combined Task5 + Task6 acceptance gates pass.
