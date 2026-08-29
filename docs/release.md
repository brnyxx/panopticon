# Installation, verification, upgrade, rollback, and release recovery

Version 1.0.1 is currently published as the `panopticon-mcp` Python package, four native archives,
and Homebrew formula `brnyxx/homebrew-tap/panopticon`. The release assets are immutable:
[PyPI](https://pypi.org/project/panopticon-mcp/1.0.1/),
[GitHub release](https://github.com/brnyxx/panopticon/releases/tag/v1.0.1), and
[Homebrew tap revision](https://github.com/brnyxx/homebrew-tap/commit/7733d8fec72c6bde2f6b9e284e29ba2c77272eb0).
The scoped npm channel is forthcoming and is not a v1.0.1 distribution.

## Choose an install method

### One-shot `uvx`

`uvx` installs into its temporary tool environment for this invocation:

```bash
uvx panopticon-mcp@1.0.1 version
uvx panopticon-mcp@1.0.1 doctor
```

### Persistent Python or Homebrew install

Choose one persistent installer:

```bash
uv tool install panopticon-mcp==1.0.1
pipx install panopticon-mcp==1.0.1
brew install brnyxx/homebrew-tap/panopticon
```

Verify every installed form with:

```bash
pano version
```

It reports `pano 1.0.1 (schema 1.0)`.

### Native archive and air-gapped install

Download the matching `linux-x86_64`, `linux-arm64`, `darwin-x86_64`, or `darwin-arm64` archive,
`SHA256SUMS`, and the archive's `.sigstore.json` bundle from the
[v1.0.1 release](https://github.com/brnyxx/panopticon/releases/tag/v1.0.1). In a connected,
trusted transfer environment, verify the downloaded archive against the release checksum:

```bash
shasum -a 256 -c SHA256SUMS
```

Transfer the verified archive and checksum file into the air-gapped environment, verify the checksum
again with the same command, extract the archive, and put `pano` on `PATH`. Retain the matching
Sigstore bundle with the archive as release provenance. No installer network access is needed after
that transfer.

`pano doctor` needs no container runtime. Local `pano watch` needs Docker or Podman. Remote
observation marks server-side file and process dimensions `UNSUPPORTED`. Native Windows supports
discovery only; use WSL2 for supported Linux observation behavior.

### Forthcoming scoped npm channel

The next patch is planned to publish root package `@brnyxx/panopticon` with exact-version optional
native packages `@brnyxx/panopticon-linux-x64-gnu`,
`@brnyxx/panopticon-linux-arm64-gnu`, `@brnyxx/panopticon-darwin-x64`, and
`@brnyxx/panopticon-darwin-arm64`. After that publication, install the root package with:

```bash
npm install -g @brnyxx/panopticon
pano version
```

The root package selects the matching native optional package; it does not download a binary during
postinstall. npm registry traffic occurs before `pano` starts and is not controlled by
`pano --offline`.

## Upgrade and rollback

Use the installer that owns the installation:

```bash
uv tool upgrade panopticon-mcp
pipx upgrade panopticon-mcp
brew upgrade panopticon
npm update -g @brnyxx/panopticon
```

For a Python rollback, pin the earlier immutable published version with `uv tool install
panopticon-mcp==VERSION` or `pipx install panopticon-mcp==VERSION`; for npm, use `npm install -g
@brnyxx/panopticon@VERSION`. Homebrew rollback uses a prior tap formula revision. Native users
restore a previously verified archive. Preserve the archive, `SHA256SUMS`, Sigstore bundle, and
release manifest for every retained version.

Configuration rollback is independent of package rollback. Run the originating `pano fix --undo`
or `pano uninstall` transaction before removing a version that created a configuration change.
Undo refuses to replace a file changed since its recorded transaction. Retain observations,
baselines, wrap logs, journals, and encrypted backups only for the period your policy requires;
the default wrap-log retention is 30 days. See [privacy](privacy.md) for local storage and cleanup.

## Maintainer promotion and recovery

The release workflow builds once, rehearses through TestPyPI, verifies retained bytes, then promotes
the same bundle. Start the rehearsal from the release commit:

```bash
gh workflow run release.yml --ref main -f channel=rehearsal
```

For production or recovery, use the successful rehearsal run's numeric ID and its exact 40-character
commit SHA as the `source_run_id` and `source_sha` workflow inputs. The workflow re-verifies the
retained bundle, PyPI files, signatures, SBOM, checksums, draft assets, and image digests; it
publishes only a missing channel and never rebuilds or overwrites published bytes. Select
`production` to promote every pending production channel or `recovery` to resume only a missing
channel.

Before the first npm publication, a human organization owner must complete npm's 2FA/trusted
publisher bootstrap for `@brnyxx`. That authorization is intentionally human-only; no repository
workflow or recovery command can create it. After bootstrap, platform packages publish before the
root package, and each package's registry integrity must match the retained release manifest before
the root package is published.
