# Product readiness — 2026-08-31

This document separates published evidence from residual limits. It does not replace the release
evidence or rerun any gate.

## Observed v1.0.2 evidence

- [PyPI v1.0.2](https://pypi.org/project/panopticon-mcp/1.0.2/) publishes the exact rehearsed wheel
  and sdist.
- The five exact scoped npm packages are public, with root package
  [`@brnyxx/panopticon@1.0.2`](https://www.npmjs.com/package/@brnyxx/panopticon/v/1.0.2)
  selecting four exact-version native optional packages.
- The public [v1.0.2 GitHub release](https://github.com/brnyxx/panopticon/releases/tag/v1.0.2)
  retains 48 assets, including checksums, SBOMs, and one Sigstore bundle for every signed file.
- [CI](https://github.com/brnyxx/panopticon/actions/runs/33382566931) and the
  [six-platform matrix](https://github.com/brnyxx/panopticon/actions/runs/33382566918) pass the
  final E20 tree.
- The signed [rehearsal](https://github.com/brnyxx/panopticon/actions/runs/33356213584/attempts/2)
  built commit `902c0e7` once; [production](https://github.com/brnyxx/panopticon/actions/runs/33383001430)
  promoted those retained bytes without rebuilding.
- The exact retained formula is public at
  [Homebrew tap revision](https://github.com/brnyxx/homebrew-tap/commit/c74b28cb03986e69705b82d8b8a89c1e65b7d493).

## Confirmed defects before this work

1. The standard self-scan path did not match its intended contract.
2. Landing-page onboarding and privacy disclosure omitted material novice-facing guidance.
3. npm distribution was absent from v1.0.1.

## E20 work delivered

- Rebuilt English and Korean landing pages as a single novice path: installation, version check,
  container-free `doctor`, one target selection, result states and rule IDs, PNG evidence, privacy,
  and rollback/cleanup.
- Made README assets and repository links absolute GitHub URLs so the PyPI rendering has usable
  assets and links.
- Expanded privacy disclosure for automatic/background upload, `--real-env`,
  `--real-env-all`, persistence rejection, installer traffic, runtime traffic, and `--offline`.
- Documented distribution paths, archive verification, retention,
  rollback, and release recovery.
- Added deterministic root plus four native npm packages that preserve the retained executable
  bytes and use no lifecycle downloader or Python bridge.
- Restored production standard scan with the declared Semgrep version and bounded exact-version
  OSV advisory lookup; offline standard scan remains explicitly `INCOMPLETE`.
- Bound production/recovery to the exact successful rehearsal and protected `npm`, `pypi`,
  `testpypi`, and `release` environments.
- Pinned the release frontend/backend, added a two-build byte comparison, modernized PyPI license
  metadata, and expanded tested Python metadata through 3.14.

## Public verification for 1.0.2

- `make ci`: 1,634 passed, one skipped, 32 Docker/network tests deselected; branch coverage 85.43%.
- Production re-verified every retained artifact before PyPI and npm, then re-downloaded every
  GitHub draft asset before making the existing draft public.
- Public PyPI SHA-256 and all five npm SHA-512 integrity values match the signed release manifest.
  The root npm package's four optional dependencies are exact `1.0.2` pins.
- All 24 public Sigstore bundles verify offline against
  `release.yml@refs/heads/main` and `https://token.actions.githubusercontent.com`.
- A no-cache public uvx invocation, isolated uv tool install, isolated npm install, checksum-verified
  native archive, Homebrew upgrade, and Homebrew formula test all report
  `pano 1.0.2 (schema 1.0)`.
- The published Pages EN/KO routes load only repository-owned runtime assets, preserve explicit
  incomplete and unsupported coverage, and pass desktop/mobile browser QA.

## Prioritized residual risks

1. **npm target boundary:** the public packages remain limited to GNU Linux x64/arm64 and macOS
   x64/arm64; do not widen the claim to musl or native Windows.
2. **Cross-repository Homebrew handoff:** the tap update remains an explicit post-promotion step.
   It must continue to use the exact attested rehearsal formula rather than rendering a replacement.
3. **Future npm publication authentication:** configure each existing package's Trusted Publisher
   before publishing another version so subsequent missing versions use GitHub OIDC rather than a
   new bootstrap token. This does not change the verified 1.0.2 bytes.

Authoritative release history remains [PROGRESS.md](https://github.com/brnyxx/panopticon/blob/main/docs/PROGRESS.md);
this readiness note is evidence-scoped to the links above.
