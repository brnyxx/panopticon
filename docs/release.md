# Release, installation, upgrade, and rollback

Panopticon 1.0.1 is the current release target for the `panopticon-mcp` Python package, four native
archives, and Homebrew formula `brnyxx/homebrew-tap/panopticon`. The existing `ghcr.io/brnyxx`
sandbox image digests remain locked; this patch does not rebuild or republish them. Release promotion
uses one signed asset bundle; later channels never rebuild it. Publication still requires the E19
gates and recorded evidence; this guide does not assert that 1.0.1 is public.

## Install

```bash
uvx panopticon-mcp@1.0.1 version
pipx install panopticon-mcp==1.0.1
brew install brnyxx/homebrew-tap/panopticon
```

For a native archive, download the archive for `linux-x86_64`, `linux-arm64`,
`darwin-x86_64`, or `darwin-arm64` from the GitHub release. Verify `SHA256SUMS` and its Sigstore
bundle before extracting it, then place `pano` on `PATH`. The executable reports
`pano 1.0.1 (schema 1.0)`.

`pano doctor` needs no container runtime. Local `pano watch` needs Docker or Podman; remote
observation reports file and process dimensions as `UNSUPPORTED`. Native Windows supports
discovery only. Use WSL2 for the supported Linux behavior and its separate evidence manifest.

## Upgrade

Use the same installer that installed Panopticon:

```bash
uv tool upgrade panopticon-mcp
pipx upgrade panopticon-mcp
brew upgrade panopticon
```

Persisted schema 0.1 baselines migrate idempotently to the frozen schema 1.0. Back up the Panopticon
data directory before an upgrade. Client configuration mutation remains journaled: preview the
change, apply it, re-check it, and retain the transaction ID for undo.

## Rollback

Python installers can pin the previous published version, including immutable 1.0.0. Homebrew can
install a prior formula revision from tap history. Native users can restore the prior verified
archive. The 1.0.0 release history and artifacts remain rollback evidence; do not rewrite or reuse a
published version.

Configuration rollback is independent of package rollback. Run the corresponding `pano fix --undo`
or `pano uninstall` transaction before removing a version that created it. Undo refuses to replace a
file changed since the recorded transaction.

## Promotion and recovery

The release order is quality and platform gates, signed artifacts, clean installs, TestPyPI, GitHub
release, PyPI, GHCR verification, then Homebrew. Before production promotion, the release handoff
records the rehearsal workflow run ID and source commit SHA with the retained bundle, manifest,
signatures, SBOM, provenance, and checksums. Production verifies that handoff and re-verifies every
retained artifact byte-for-byte against the rehearsal manifest before any channel is promoted.

A failed channel leaves earlier immutable bytes and hashes untouched. Recovery resumes only the
missing channel from the retained release bundle after the same handoff and byte-for-byte
re-verification; it never rebuilds, overwrites, or reuses a published version.

The exhaustive outbound-product-path table—including registry/package installation, observed and
remote MCP traffic, FIX-008 validation, and approved `scan --mode deep` requests—is in
[privacy](privacy.md). `--offline` disables every path in that table. Retention, semantic
disclosure, and cleanup details are in [privacy](privacy.md) and [limitations](limitations.md).
