# Privacy

Panopticon is local-first. It has no telemetry, crash reporting, update ping, background upload,
or automatic upload. Product traffic happens only when you invoke a feature. The exhaustive list
of runtime outbound traffic follows.

## What leaves your machine at runtime

| When | Destination | What | Your key needed |
|---|---|---|---|
| `doctor`, `diff` (HIST rules) | registry.npmjs.org, pypi.org, api.github.com | package names only; `GITHUB_TOKEN` is used if set and is leak-checked before anything is written | no |
| `watch` / `scan --mode deep` | package registries, from inside the sandbox | package-install traffic | no |
| `watch` | wherever the *MCP under test* connects, inside the sandbox through the logging proxy | whatever the MCP sends, with decoy values by default | no |
| remote `watch` | configured remote MCP endpoint | bounded MCP JSON-RPC requests; configured real header values leave only when explicitly permitted and are never persisted | maybe |
| `fix` for FIX-008, unless `--offline` | configured remote MCP endpoint | one bounded unauthenticated MCP `initialize` request proving the HTTPS endpoint before a config rewrite; no configured authentication header is sent | no |
| `scan --mode deep` | your model provider's API | redacted source excerpts, shown to you before they are sent | yes |

Nothing else leaves through Panopticon runtime paths.

### Environment values

By default, the target receives decoy environment values. `watch --real-env KEY1,KEY2` deliberately
passes only the selected declared environment values to the target. `watch --real-env-all`
deliberately passes every declared environment value to the target and prints a warning. These
options are mutually exclusive and cannot be used with `--self`. Values passed by either option
are not persisted by Panopticon, but the target can transmit values it receives; use them only when
that disclosure is intended.

### Installer traffic is separate

`uvx`, `uv tool`, `pipx`, Homebrew, archive downloads, and the forthcoming npm installer contact
their own package registries or download hosts before `pano` starts. That traffic is controlled by
the installer and its network configuration, **not** by `pano --offline`. Once running,
`pano --offline` disables the runtime paths described below.

## The semantic analyzer is the explicit source-sharing feature

`scan --mode deep` is the only feature that sends your source anywhere:

- It runs only when you choose deep mode; quick and standard do not call it.
- It uses your API key. Panopticon ships no credential and no default endpoint account.
- Before the first request, it prints exactly what will be sent.
- Only redacted excerpts leave; secrets and paths are stripped first.
- `--offline` disables it. The semantic result is typed `UNSUPPORTED` and the scan is
  `INCOMPLETE`.

## What is stored locally

`~/.panopticon/` (0700) holds observations, baselines, wrap logs, cache, journal, and backups.
One persistence gateway canonicalizes each artifact and runs the leak check before writing. An
artifact containing raw token values, absolute home paths, values supplied through `--real-env` or
`--real-env-all`, or plaintext Panopticon-managed secret material is rejected rather than stored.

Secrets that a fix needs to relocate go into your OS credential store (macOS Keychain, Linux Secret
Service, Windows Credential Manager). Backups of secret-bearing configs are encrypted with
authenticated encryption whose key lives in that same credential store. Without a usable credential
store, Panopticon provides manual guidance and writes nothing.

Wrap records rotate daily and are retained for 30 days by default (`config.toml`). Remove retained
records, observations, baselines, cache, journals, and backups according to your retention policy;
use the originating `pano fix --undo` or `pano uninstall` transaction before deleting the package
version that created a configuration change.

## What never enters a container

Your home directory, project files (only their names are replicated as empty files), and environment
variables (replaced by decoys unless you explicitly pass them). The one permitted mount is `--self`,
which mounts your MCP source read-only so it can be built and observed.

## `--offline`

`--offline` disables registry lookups, sandbox package-install traffic, FIX-008 endpoint validation,
the semantic analyzer, and every other Panopticon runtime outbound call. Cached registry data may
still be read; when it is missing, results are `UNKNOWN`. An offline FIX-008 request is
guidance-only and does not change the configured URL.
