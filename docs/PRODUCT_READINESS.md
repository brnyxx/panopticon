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

## Pending human action

The first npm publication is blocked on a human npm organization owner completing the
2FA/trusted-publisher bootstrap for `@brnyxx`. This cannot be performed by repository automation.
Until it is complete, the scoped npm package and its four platform packages are planned distribution
artifacts, not published evidence.

## Prioritized residual risks

1. **Highest — standard self-scan:** rerun the relevant release and platform evidence after the
   contract fix; the existing v1.0.1 evidence predates that correction.
2. **High — npm publication:** complete the human bootstrap, then prove platform-first publication,
   root-package integrity, installation, upgrade, and recovery from retained artifacts.
3. **Medium — documentation behavior:** run the repository documentation and phrase gates after
   these wording changes; they have not been run for this work.
4. **Medium — installer boundaries:** validate each installer path on a clean environment and keep
   its network traffic distinction from `pano --offline` visible.

Authoritative release history remains [PROGRESS.md](https://github.com/brnyxx/panopticon/blob/main/docs/PROGRESS.md);
this readiness note is evidence-scoped to the links above.
