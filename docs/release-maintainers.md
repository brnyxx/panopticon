# Maintainer release promotion and recovery

This document is for Panopticon release maintainers. End users should use
[Getting started](getting-started.md) and [installation, upgrade, and rollback](release.md).
The scoped npm channel remains unpublished until the recorded 1.0.2 rehearsal and human bootstrap
complete; none of the commands below make it a public 1.0.1 channel.

## Build-once promotion

The release workflow builds once, rehearses through TestPyPI, verifies retained bytes, then promotes
the same bundle. The repository workflow owns PyPI, npm, and GitHub publication. The Homebrew tap
update remains a separate cross-repository step: the rehearsal's required `homebrew-handoff` job
verifies the retained bundle, renders `Formula/panopticon.rb` from its manifest, attests it, and
uploads `homebrew-formula-VERSION`. After the GitHub release becomes public, commit that exact
formula to `brnyxx/homebrew-tap` and require `brew audit`, install, and version checks before the
release is closed.

Start the rehearsal from the release commit:

```bash
gh workflow run release.yml --ref main -f channel=rehearsal
```

The workflow enforces `refs/heads/main` at the job boundary for every build, rehearsal, production,
and recovery channel. Production preflight also requires the retained rehearsal run's
`headBranch` to be `main`; documentation or caller discipline is not the provenance control.

For production or recovery, use the successful rehearsal run's numeric ID and its exact 40-character
commit SHA as the `source_run_id` and `source_sha` workflow inputs. The workflow re-verifies the
retained bundle, PyPI files, signatures, SBOM, checksums, draft assets, and image digests. It
publishes only a missing channel and never rebuilds or overwrites published bytes.

Select `production` to promote every pending production channel or `recovery` to resume only a
missing channel. Before either path, the checked-in preflight binds those inputs to the successful
`release` workflow dispatch and requires protected branches, a reviewer, and disabled admin bypass
on the `npm`, `pypi`, `testpypi`, and `release` environments.

## One-time exact-artifact npm bootstrap

Before the first npm publication, a human organization owner must complete npm's 2FA and trusted
publisher bootstrap for `@brnyxx`. No repository workflow or recovery command can create that
authorization. Perform this only after the 1.0.2 rehearsal succeeds and its approvals are complete.

Download both artifacts from that exact run, then verify the retained manifest before logging in to
npm:

```bash
export RUN_ID=SUCCESSFUL_REHEARSAL_RUN_ID
export SOURCE_SHA=EXACT_40_CHARACTER_RELEASE_SHA
export VERSION=1.0.2
gh run download "$RUN_ID" --name "release-bundle-$VERSION" --dir recovery-bundle
gh run download "$RUN_ID" --name npm-distributions --dir npm-dist
python scripts/verify_release_recovery.py bundle \
  --version "$VERSION" --source-sha "$SOURCE_SHA" --bundle recovery-bundle
python - <<'PY'
from pathlib import Path

tarballs = sorted(Path("npm-dist").glob("*.tgz"))
if len(tarballs) != 5:
    raise SystemExit("NPM_BOOTSTRAP_TARBALL_COUNT")
for tarball in tarballs:
    retained = Path("recovery-bundle", tarball.name)
    if not retained.is_file() or retained.read_bytes() != tarball.read_bytes():
        raise SystemExit(f"NPM_BOOTSTRAP_ARTIFACT_MISMATCH:{tarball.name}")
PY
```

The npm organization owner authenticates with 2FA and publishes the exact downloaded files, four
platform packages first and the root package last:

```bash
npm login
npm publish "npm-dist/brnyxx-panopticon-linux-x64-gnu-$VERSION.tgz" --access public
npm publish "npm-dist/brnyxx-panopticon-linux-arm64-gnu-$VERSION.tgz" --access public
npm publish "npm-dist/brnyxx-panopticon-darwin-x64-$VERSION.tgz" --access public
npm publish "npm-dist/brnyxx-panopticon-darwin-arm64-$VERSION.tgz" --access public
npm publish "npm-dist/brnyxx-panopticon-$VERSION.tgz" --access public
```

Configure the GitHub trusted publisher for all five packages after their creation, then rerun the
production or recovery workflow with the same `RUN_ID` and `SOURCE_SHA`. The workflow refuses a
missing package with `NPM_PACKAGE_BOOTSTRAP_REQUIRED`, compares each registry `dist.integrity`
against the retained tarball, and releases GitHub assets only after npm and PyPI match.

## Recovery invariants

- Use only the successful rehearsal run and exact source SHA recorded for the release.
- Never rebuild a production or recovery artifact.
- Re-verify signatures, SBOM, checksums, image digests, and registry integrity before continuing.
- Publish platform npm packages before the root package.
- Keep the GitHub release dependent on exact PyPI and npm integrity.
- Record Homebrew handoff evidence separately because it crosses repositories.

The frozen release contracts and human-only gates are in
[`panopticon-buildplan.md`](../panopticon-buildplan.md),
[`docs/PRODUCT_READINESS.md`](PRODUCT_READINESS.md), and [`docs/PROGRESS.md`](PROGRESS.md).
