# Installation, verification, upgrade, and rollback

Version 1.0.1 is currently published as the `panopticon-mcp` Python package, four native archives,
and Homebrew formula `brnyxx/homebrew-tap/panopticon`. The release assets are immutable:
[PyPI](https://pypi.org/project/panopticon-mcp/1.0.1/),
[GitHub release](https://github.com/brnyxx/panopticon/releases/tag/v1.0.1), and
[Homebrew tap revision](https://github.com/brnyxx/homebrew-tap/commit/7733d8fec72c6bde2f6b9e284e29ba2c77272eb0).
The scoped npm channel is forthcoming and is not a v1.0.1 distribution.
The checked-out repository is unpublished 1.0.2 development; its `uv sync --all-extras` setup is
for contributors and is not one of the public install methods below.

First-time users should follow [Getting started](getting-started.md). Automation agents should use
the confirmation boundaries and JSON response contract in [the agent operating guide](agent-guide.md).
Release maintainers use the separate [promotion and recovery guide](release-maintainers.md).

## Choose an install method

| Method | Use it when | Network before `pano` | Owner for upgrade/rollback |
|---|---|---|---|
| `uvx` | You want a one-shot invocation | PyPI through uv | Temporary environment; pin every invocation |
| `uv tool` | uv owns persistent command-line tools | PyPI through uv | uv |
| `pipx` | pipx owns isolated Python applications | PyPI through pip/pipx | pipx |
| Homebrew | Homebrew owns system command-line tools | GitHub/Homebrew hosts | Homebrew tap |
| Native archive | You need a standalone binary or air-gapped transfer | GitHub release host before transfer | Your verified archive inventory |

Package installation traffic happens before Panopticon starts and is not controlled by
`pano --offline`.

### One-shot `uvx`

```bash
uvx --from 'panopticon-mcp==1.0.1' pano version
uvx --from 'panopticon-mcp==1.0.1' pano doctor --offline
uvx --from 'panopticon-mcp==1.0.1' pano watch SERVER_NAME --offline
```

`uvx` installs into a temporary tool environment for each invocation.
Use the complete `uvx --from ... pano` prefix for every one-shot command.

### Persistent Python or Homebrew install

Choose one persistent installer:

```bash
uv tool install panopticon-mcp==1.0.1
# or
pipx install panopticon-mcp==1.0.1
# or
brew install brnyxx/homebrew-tap/panopticon
```

Verify every installed form with:

```bash
pano version
```

It reports `pano 1.0.1 (schema 1.0)`.

## Native archive and air-gapped install

Download the matching `linux-x86_64`, `linux-arm64`, `darwin-x86_64`, or `darwin-arm64` archive,
`SHA256SUMS`, and the archive's `.sigstore.json` bundle from the
[v1.0.1 release](https://github.com/brnyxx/panopticon/releases/tag/v1.0.1).

In a connected, trusted transfer environment, verify the downloaded archive against the release
checksum:

```bash
export ARCHIVE=panopticon-1.0.1-darwin-arm64.tar.gz
awk -v file="$ARCHIVE" '$2 == file' SHA256SUMS | shasum -a 256 -c -
```

Verify the keyless signature against the exact release workflow identity. Set `ARCHIVE` to the
downloaded filename; `uvx sigstore` contacts PyPI when the verifier is not already installed:

```bash
uvx sigstore verify identity \
  --bundle "$ARCHIVE.sigstore.json" \
  --cert-identity \
  "https://github.com/brnyxx/panopticon/.github/workflows/release.yml@refs/heads/main" \
  --cert-oidc-issuer "https://token.actions.githubusercontent.com" \
  "$ARCHIVE"
```

Use the filename for your platform. Retain the matching Sigstore bundle with the archive as
provenance. Transfer the archive, checksum, and bundle into the air-gapped environment, verify the
checksum again, extract the archive, and put `pano` on `PATH`. No installer network access is
needed after transfer.

`pano doctor` needs no container runtime. Local `pano watch` needs Docker or Podman and its
pinned sandbox image; offline observation cannot pull a missing image. Remote observation marks
server-side file and process dimensions `UNSUPPORTED`. Native Windows supports discovery only; use
WSL2 for supported Linux observation behavior.

## Forthcoming scoped npm channel

The next patch is designed to publish root package `@brnyxx/panopticon` with exact-version optional
native packages for Linux GNU x64/arm64 and macOS x64/arm64. It is not an installation option until
registry publication and public clean-install evidence exist.

After that publication, the documented install will be:

```bash
npm install -g @brnyxx/panopticon
pano version
```

The root package selects the matching native optional package. It has no lifecycle download script,
and npm registry traffic occurs before `pano` starts.

## Upgrade and rollback

Use the installer that owns the current installation:

```bash
uv tool upgrade panopticon-mcp
pipx upgrade panopticon-mcp
brew upgrade panopticon
```

For Python rollback, replace `VERSION` with an immutable published version:

```bash
uv tool install "panopticon-mcp==VERSION" --force
# or
pipx install "panopticon-mcp==VERSION" --upgrade
pano version
```

For Homebrew, extract the retained formula history into a version tap. Replace
`YOUR_GITHUB_USER` with the tap owner you control:

```bash
brew tap-new YOUR_GITHUB_USER/panopticon-versions
brew extract --version=1.0.1 \
  brnyxx/homebrew-tap/panopticon \
  YOUR_GITHUB_USER/panopticon-versions
brew install YOUR_GITHUB_USER/panopticon-versions/panopticon@1.0.1
ROLLBACK_PREFIX="$(brew --prefix YOUR_GITHUB_USER/panopticon-versions/panopticon@1.0.1)"
"$ROLLBACK_PREFIX/bin/pano" version
```

That verifies the restored keg without changing the active command. To make it active, review the
current links, then explicitly switch and verify:

```bash
brew unlink panopticon
brew link --force YOUR_GITHUB_USER/panopticon-versions/panopticon@1.0.1
pano version
```

Native users extract a previously checksum- and signature-verified archive into a versioned
directory and verify that exact binary before changing the active path:

```bash
export ARCHIVE=panopticon-1.0.1-darwin-arm64.tar.gz
export ROLLBACK_ROOT="$HOME/.local/opt/panopticon/1.0.1"
mkdir -p "$ROLLBACK_ROOT"
tar -xzf "$ARCHIVE" -C "$ROLLBACK_ROOT" --strip-components=1
"$ROLLBACK_ROOT/pano" version
```

After it reports `pano 1.0.1 (schema 1.0)`, back up the path owned by the prior native install,
replace that path with the verified binary or a symlink to it, and invoke that exact active path
with `version` again. Do not overwrite a uv, pipx, or Homebrew-owned executable with this branch.
Preserve the archive, `SHA256SUMS`, Sigstore bundle, and release manifest for every retained
version.

After a scoped npm release is publicly verified, npm users upgrade or roll back with
`npm update -g @brnyxx/panopticon` or `npm install -g @brnyxx/panopticon@VERSION`. These commands are
not a v1.0.1 installation path. Run `pano version` after either operation.

## Configuration rollback is separate

Run the originating `pano fix --undo TRANSACTION_ID` or `pano uninstall CLIENT --dry-run` before
removing a version that created a configuration change. Undo refuses to replace a file changed
since its transaction. Preview an uninstall, then apply with `--yes` only after reviewing the exact
restore.

Retain observations, baselines, wrap records, journals, and encrypted backups only for the period
your policy requires; default wrap retention is 30 days. Storage and cleanup are specified in
[privacy.md](privacy.md).

## Maintainer release operations

Build-once rehearsal, protected promotion, exact-artifact recovery, Homebrew handoff, and the
human-only npm bootstrap live in [Maintainer release promotion and recovery](release-maintainers.md).
Those commands are not part of end-user installation.
