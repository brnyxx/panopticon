# Decisions

Numbered, append-only. Format: context / options / chosen / why.

## 1. Container image registry org
- Context: E05 needs a home for `pano-sandbox-*` images (panopticon-buildplan.md §8).
- Options: `ghcr.io/<personal>`, `ghcr.io/<org>`, Docker Hub.
- Chosen: **`ghcr.io/brnyxx`**. Image references are `ghcr.io/brnyxx/pano-sandbox-base`, `pano-sandbox-node:20`, `pano-sandbox-node:22`, `pano-sandbox-python:3.12`.
- Why: the release targets already live under the `brnyxx` account, GHCR inherits repository authentication and OIDC signing, and one namespace keeps `sandbox/images.lock` digests, package permissions, and Sigstore identities in a single trust domain. Packages stay non-public until the release publishes them (E19).

## 2. Initial network allowlist
- Context: WATCH-003/005 need an install-time allowlist (panopticon-buildplan.md §15).
- Chosen: the list in `analyzers/behavior/allow.yaml` (registry + GitHub release CDN only). Revisit when a fixture shows a false positive.

## 3. `wrap` OS notification default
- Chosen: off. Alerts are surfaced by the next `pano doctor`. `--notify` opts in.

## 4. Host wildcard syntax in `.panopticon.yaml`
- Chosen: leading `*.` only (`*.example.com`). No mid-label globs. Matches allow.yaml semantics.

## 5. PNG card design
- Context: E17 needs one shareable evidence artifact that carries observation results without becoming marketing decoration.
- Options: marketing-style hero card, minimal badge-only image, terminal-style evidence card.
- Chosen: **deterministic high-contrast terminal-style evidence card**. It renders the same sanitized model the terminal reporter uses: server identity, observation date, per-stage coverage with visible `UNKNOWN`/`UNSUPPORTED`, declared-versus-observed differences, and finding counts by kind. Bundled fonts, fixed layout and color tokens, fixed compression, stripped metadata, ko/en text.
- Why: accessibility and leak-safe rendering outrank decoration, and byte-stable output is testable by golden hash. The card carries no verdict term and never implies a pass.

## 6. Persisted schema lifecycle
- Context: the scaffold hard-codes `schema_version: "1.0"` in `schemas/*.json` while §21 and §23 require 0.x migrators before a 1.0 freeze.
- Options: freeze 1.0 now, keep an unversioned line, develop on 0.x and freeze once at release.
- Chosen: **develop on `0.1`, bump within the 0.x line for every breaking shape change with an idempotent migrator, and migrate to `1.0` exactly once at the 0.9 release-candidate gate.**
- Why: a public compatibility promise cannot be made before the shapes are proven by real observations. Freezing early would either lock in wrong shapes or force silent redefinition of a published version.

## 7. Installation identity versus server identity
- Context: one `server_id` cannot address a specific config entry when the same package is installed in several clients or scopes.
- Chosen: **keep `server_id` as the group identity and add `installation_id` as the per-entry identity**, defined as a stable hash of `client | normalized config path | scope | JSON pointer | entry name`.
- Why: observations, baselines, wrap records, suppressions, fixes, and diff all address a specific installed entry. Grouping stays a reporting concern.

## 8. Stage results carry structure, not strings
- Context: a bare stage string cannot say whether missing evidence means complete, unsupported, skipped, timed out, or failed.
- Chosen: **every stage result carries an exhaustive status, a stable `reason_code`, and explicit coverage dimensions.** Absent evidence under incomplete coverage is `UNKNOWN`.
- Why: rules and diff both branch on why evidence is missing. Without the reason, absence silently reads as a pass.

## 9. One persistence gateway
- Context: the leak-check and determinism invariants quantify over every persisted artifact.
- Chosen: **`store/` is the only module allowed to write persisted artifacts**, and it runs typed normalization, versioned canonical serialization, mandatory leak scan, restrictive temp write, fsync, and symlink-safe atomic replace. `fix`/`install` config patching is the one narrow exception and follows the same journal, backup, and leak rules. A checker enforces the boundary.
- Why: duplicating the persist path is how a leak eventually ships.

## 10. Secret storage and backups
- Context: FIX-001 plaintext env files and exact config backups can hold raw tokens, which the leak invariant forbids.
- Chosen: **a typed `SecretStore` backed by the OS credential store** (macOS Keychain, Linux Secret Service, Windows Credential Manager). Secret-bearing config backups are encrypted with authenticated encryption whose key lives in the credential store. **When no secure backend is available, the fix is guidance-only** and nothing secret-bearing is written.
- Why: the alternative is a plaintext secret file created by a tool whose main promise is that secrets do not leak.

## 11. Dual-era MCP support
- Context: the current official MCP specification is `2026-07-28` and moves lifecycle and version negotiation from the `initialize` handshake to per-request metadata; older servers still require the legacy handshake.
- Chosen: **implement both eras explicitly.** Modern first with per-request metadata, server discovery, and version retry; legacy `initialize`/`notifications/initialized` on typed fallback; Streamable HTTP with deprecated HTTP+SSE fallback. Every observation records the requested version, the selected version, the era, and the fallback reason.
- Why: silent fallback makes observations incomparable across runs, and a modern-only client cannot observe most installed servers.

## 12. Semantic analysis is the one user-invoked network exception
- Context: `scan --mode deep` sends redacted source excerpts to a hosted model.
- Chosen: **the semantic analyzer is an explicit exception to local-only operation.** It runs only when the user selects deep mode and supplies their own API key, prints the exact payload disclosure before the first request, sends redacted excerpts only, and is disabled by `--offline`. With `--offline`, semantic results are typed `UNSUPPORTED` and the scan result is `INCOMPLETE`, never a pass.
- Why: an undisclosed outbound call would contradict the product's central claim. A disclosed, user-invoked, user-keyed exception does not.

## 13. Upstream provenance is pinned, not inherited
- Context: the buildplan originally said the repository forks upstream Git history.
- Chosen: **vendor only the required MCP-Sentinel files and the 125-test corpus from pinned commit `e717e955`**, preserving MIT headers and recording a per-file provenance and checksum manifest plus `THIRD_PARTY_NOTICES.md` entries.
- Why: the working history is the local scaffold, not upstream. Pinned provenance is verifiable by hash; ancestry claims are not.

### 13a. Read-only upstream reference clone (clarification, not a scope change)
- Context: adapting upstream analyzers sometimes needs the surrounding business logic, which a per-file copy at the pinned commit doesn't show in context.
- Chosen: an implementer **may clone `https://github.com/BashaarJavaid/MCP-Sentinel` into a disposable directory outside the repository and read it**, under these limits:
  - The clone is **reference only**. The single vendorable source stays exact commit `e717e955`.
  - Never modify the clone, and never vendor content from a moving branch such as `main`.
  - Never import upstream Git ancestry into this repository.
  - Every vendored file keeps its MIT header and lands in the per-file provenance and checksum manifest.
  - The selected upstream test IDs are enumerated explicitly, not described as a count.
  - After task 21, delete the clone and prove the path is absent.
- Why: reading upstream in context is how the adaptation stays faithful. Bounding it to a disposable read-only copy keeps the provenance claim exactly as strong as before: everything shipped still resolves to `e717e955` by hash.

## 14. Vulnerability intake
- Context: `SECURITY.md` advertised a `security@<domain>` address that does not exist.
- Chosen: **GitHub Private Vulnerability Reporting on `brnyxx/panopticon` is the only official intake.**
- Why: an unmonitored mailbox is worse than no mailbox. Private reporting is authenticated, tracked, and needs no published address.

## 15. Forbidden verdict terms
- Context: ground rule 1 lists forbidden verdict words; `src/panopticon/i18n/glossary.yaml` holds the machine-checked phrase list that `scripts/check_phrases.py` enforces.
- Chosen: **the authoritative phrase set is `src/panopticon/i18n/glossary.yaml` (`forbidden.en`, `forbidden.ko`), and the authoritative term-level rule is ground rule 1 in `AGENTS.md`: `safe`, `certified`, `dangerous` (as a verdict), `perfect`, `100%`.** A numeric safety score is a separately prohibited claim, not a phrase in this list. Adding a term requires amending the glossary, `AGENTS.md`, and this entry in the same change.
- Why: one named source of truth stops the linter, the glossary, and the prose from drifting apart. Enumerating the set in three places by hand is how they diverge.

## 16. Release history normalization is archived first
- Context: the local scaffold and the one-commit remote `main` share no merge base.
- Chosen: **push the immutable tag `archive/pre-normalization-main-20260826` at the old remote root, then replace `origin/main` once with `--force-with-lease`.** Tag names in this family are normalized as `archive/<reason>-<YYYYMMDD>`. No later force push is authorized.
- Why: the old history stays recoverable by ref, and the lease makes the one-time replacement fail closed if the remote moved.

## 17. Wrap records are immutable per installation and tool span
- Context: an append-only daily NDJSON file requires a cross-process lock around read, leak scan,
  canonicalization, replace, and retention. A crash or uncooperative writer can corrupt the whole
  day, and a `server_id` directory conflates separate client installations.
- Chosen: **persist one canonical `WrapRecord` JSON artifact per `installation_id`, UTC day, and
  stable `span_id` through `store/`**. Daily directories are the rotation boundary; retention removes
  expired day directories. Atomic per-record replacement makes concurrent identical writes
  deterministic without an append lock.
- Why: the runtime schema already models one wrap record, `installation_id` is the addressable
  config identity (DECISIONS #7), and immutable artifacts retain the store's leak and crash-safety
  guarantees without a shared mutable log.

## 18. Outbound product paths are exhaustive and user-invoked
- Context: remote MCP observation and FIX-008 HTTPS validation are shipped network operations, while
  DECISIONS #12 used "one network exception" to describe the narrower act of sending user source to
  a hosted model. Treating that phrase as the complete traffic inventory made the public summary
  contradict the implemented, disclosed behavior.
- Chosen: **`docs/privacy.md` is the exhaustive outbound-product-path table.** The allowed paths are
  registry and sandbox package-install lookups, the observed MCP's sandbox traffic, explicitly
  permitted remote `watch` traffic, bounded unauthenticated FIX-008 validation, and user-invoked
  deep semantic review. Deep review remains the only path that sends redacted user source to a
  hosted model. `--offline` disables every outbound path.
- Why: prohibiting telemetry and undisclosed traffic is compatible with bounded operations the user
  explicitly requests. One exhaustive table prevents concise summaries and runtime behavior from
  drifting apart.

## 19. Patch releases resolve their version from `pyproject.toml`
- Context: patch-release scripts and workflows previously repeated a release version, which can
  drift from package metadata and makes rehearsal-to-production handoff ambiguous.
- Options: retain separately maintained version values; derive a version dynamically in each caller;
  or use one checked-in resolver reading `pyproject.toml`.
- Chosen: **`[project].version` in `pyproject.toml` is the sole patch-release authority.** A
  checked-in resolver validates a stable `X.Y.Z` version and supplies only controlled workflow
  outputs. Schema `1.0` remains frozen. Patch releases reuse locked GHCR digests and retained
  rehearsal artifacts; their handoff records the rehearsal run ID and source SHA, and production or
  recovery re-verifies the retained bytes exactly. Published versions, including 1.0.0, are
  immutable and are never overwritten or reused.
- Why: one authoritative package version prevents release metadata drift, while a checked-in,
  constrained resolver keeps workflow data auditable. Reusing retained evidence and locked image
  digests preserves the build-once and immutable-publication guarantees without changing product
  behavior.

## 20. npm distribution promotes retained native artifacts
- Context: npm users need a native `pano` distribution without turning npm installation into a
  networked Python launcher or creating a second version authority.
- Chosen: **the five frozen package names are `@brnyxx/panopticon`,
  `@brnyxx/panopticon-linux-x64-gnu`, `@brnyxx/panopticon-linux-arm64-gnu`,
  `@brnyxx/panopticon-darwin-x64`, and `@brnyxx/panopticon-darwin-arm64`.** The root package has
  exact-version optional dependencies on the four native packages. Its launcher has no install
  script, network access, persistence, or Python feature import; it only execs the retained binary
  for the installed matching platform. The supported native boundary is GNU Linux x64/arm64 and
  macOS x64/arm64. `[project].version` in `pyproject.toml` remains the sole version authority and
  schema `1.0` remains frozen.
- **npm promotion is platform packages first, root last, from the signed rehearsal tarballs
  only.** An existing package version is reused only when its registry integrity exactly matches the
  retained tarball; otherwise promotion fails. The npm installer boundary is distinct from
  `pano --offline`: installation may resolve a selected native package, while `--offline` disables
  all product outbound paths after installation. First creation of each npm package is a documented
  human 2FA bootstrap using the exact retained artifact; later trusted publication is OIDC-only.
  Production and recovery download and re-verify the retained npm artifacts and resume the
  platform-first/root-last order without rebuilding or overwriting.
- Why: exact optional dependencies let npm fetch only the matching native package without a
  postinstall downloader, retain build-once evidence, and make partial-publication recovery
  deterministic without adding a launcher network or Python dependency.

## 21. Standard scan advisory lookup sends exact package coordinates only
- Context: E16 requires OSV/advisory lookup in standard mode, but the production CLI previously
  supplied no advisory adapter and the exhaustive privacy inventory did not name its destination.
- Chosen: **standard and deep scans may send normalized PyPI package names and exact versions
  resolved from lock data to `https://api.osv.dev/v1/querybatch`.** The request contains no source,
  path, environment value, or credential; the response remains in memory and is never persisted.
  Missing or ambiguous versions, malformed responses, and network failures are typed
  `INCOMPLETE`. `--offline` makes the advisory dimension `UNSUPPORTED` and the whole standard/deep
  scan `INCOMPLETE`; it never falls back to quick mode.
- Why: exact coordinates make advisory evidence meaningful, one bounded batch makes the outbound
  path auditable, and explicit incomplete states preserve the product's unknown-evidence contract.
