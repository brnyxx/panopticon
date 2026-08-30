# Product readiness — 2026-08-30

This document separates published evidence from work planned for the next patch. It does not replace
the release evidence or rerun any gate.

## Observed v1.0.1 evidence

- [PyPI v1.0.1](https://pypi.org/project/panopticon-mcp/1.0.1/) publishes the Python package.
- The [v1.0.1 GitHub release](https://github.com/brnyxx/panopticon/releases/tag/v1.0.1) provides
  the retained release assets.
- [Patch CI](https://github.com/brnyxx/panopticon/actions/runs/33257641232) and the
  [six-platform matrix](https://github.com/brnyxx/panopticon/actions/runs/33257641129) are the
  published CI/platform evidence for commit `1f92491`.
- [Release promotion](https://github.com/brnyxx/panopticon/actions/runs/33258298469/attempts/2)
  and the [Homebrew tap revision](https://github.com/brnyxx/homebrew-tap/commit/7733d8fec72c6bde2f6b9e284e29ba2c77272eb0)
  record the release-path evidence.
- The repository's [local release-gate implementation](https://github.com/brnyxx/panopticon/blob/main/scripts/release_gate.py)
  defines the local gate; this document records no local execution of it.

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
- Documented released and forthcoming distribution paths, archive verification, retention,
  rollback, and release recovery.
- Added deterministic root plus four native npm packages that preserve the retained executable
  bytes and use no lifecycle downloader or Python bridge.
- Restored production standard scan with the declared Semgrep version and bounded exact-version
  OSV advisory lookup; offline standard scan remains explicitly `INCOMPLETE`.
- Bound production/recovery to the exact successful rehearsal and protected `npm`, `pypi`,
  `testpypi`, and `release` environments.
- Pinned the release frontend/backend, added a two-build byte comparison, modernized PyPI license
  metadata, and expanded tested Python metadata through 3.14.

## Local verification for the 1.0.2 candidate

- `make ci`: 1,608 passed, 1 skipped, 32 Docker/network tests deselected; branch coverage 85.29%.
- Python 3.13 and 3.14 non-Docker/network runs: 1,605 passed and 1 skipped on each interpreter.
- Online `pano ci . --mode standard --fail-on never`: `COMPLETE`, 15 repository findings, SARIF
  persisted. Offline standard scan: `INCOMPLETE`, as required.
- Two clean 1.0.2 wheel/sdist builds matched byte for byte; `twine check` passed. Wheel metadata
  contains `License-Expression: MIT`, both license/notice files, and Python 3.11–3.14 classifiers.
- The npm packager consumed the four retained 1.0.1 native archives, produced five deterministic
  local tarballs, installed root plus Darwin arm64 payload with scripts and registry fallback
  disabled, and reported `pano 1.0.1 (schema 1.0)`. The 1.0.2 signed bundle is still pending.
- The environment-bound release preflight returned `PASS` for the exact successful 1.0.1 rehearsal
  after all four GitHub release environments received protected-branch, required-reviewer, and
  no-admin-bypass policy. The current candidate adds the required `homebrew-handoff` evidence and
  correctly reports that older rehearsal `BLOCKED`; a new 1.0.2 rehearsal must produce it.
- `uv pip check` passed and `pip-audit` found no known vulnerability in resolved third-party
  dependencies; unpublished local `panopticon-mcp` 1.0.2 was not available for registry lookup.

## Pending human action

The first npm publication is blocked on a human npm organization owner completing the
2FA/trusted-publisher bootstrap for `@brnyxx/panopticon` and its four platform packages. This
cannot be performed by repository automation. Until it is complete, the scoped npm package and its
four platform packages are planned distribution artifacts, not published evidence. A signed 1.0.2
rehearsal and exact npm/PyPI promotion must follow that bootstrap; local checks do not replace them.

## Prioritized residual risks

1. **Highest — public npm/PyPI evidence:** complete the human bootstrap, signed rehearsal,
   platform-first npm publication, exact PyPI promotion, and clean public install/recovery checks.
2. **High — hosted matrix evidence:** local Python 3.13/3.14 checks pass, but the expanded hosted
   Python and six-platform workflows have not run on this candidate commit.
3. **High — npm Linux boundary:** prove the declared GNU libc baseline on both Linux architectures;
   do not widen the package claim to musl or native Windows.
4. **Medium — Homebrew orchestration:** the rehearsal now generates and attests the 1.0.2 formula
   handoff from the retained manifest, but committing that exact formula to the separate tap and
   running its public install checks remain separately operated release steps.

Authoritative release history remains [PROGRESS.md](https://github.com/brnyxx/panopticon/blob/main/docs/PROGRESS.md);
this readiness note is evidence-scoped to the links above.
