# Privacy

Panopticon is local-first. It has no telemetry, no crash reporting, no update ping, and no upload path. The complete list of outbound traffic follows.

## What leaves your machine

| When | Destination | What | Your key needed |
|---|---|---|---|
| `doctor`, `diff` (HIST rules) | registry.npmjs.org, pypi.org, api.github.com | package names only; `GITHUB_TOKEN` is used if set and is leak-checked before anything is written | no |
| `watch` / `scan --mode deep` | package registries, from inside the sandbox | package install traffic | no |
| `watch` | wherever the *MCP under test* connects, inside the sandbox, through the logging proxy | whatever the MCP sends, with decoy values, never your real ones unless you pass `--real-env` | no |
| remote `watch` | the configured remote MCP endpoint | bounded MCP JSON-RPC requests; configured real header values leave only when you explicitly permit them, and are never persisted | maybe |
| `scan --mode deep` | your model provider's API | redacted source excerpts, shown to you before they are sent | yes |

Nothing else.

## The semantic analyzer is the one explicit exception

`scan --mode deep` is the only feature that sends your source anywhere, and it's built so you can't be surprised by it:

- It runs only when you choose deep mode. Quick and standard never call it.
- It uses **your** API key. Panopticon ships no credential and no default endpoint account.
- Before the first request, it prints exactly what will be sent.
- Only redacted excerpts leave; secrets and paths are stripped first.
- `--offline` disables it. The semantic result is then typed `UNSUPPORTED` and the scan is `INCOMPLETE`, never a pass.

## What is stored locally

`~/.panopticon/` (0700): observations, baselines, wrap logs, cache, journal, backups. Every file is written by one gateway that canonicalizes it and runs the leak check first: no raw tokens, no absolute home paths, no `--real-env` values, no plaintext Panopticon-managed secret material.

Secrets that a fix needs to relocate go into your OS credential store (macOS Keychain, Linux Secret Service, Windows Credential Manager). Backups of secret-bearing configs are encrypted with authenticated encryption whose key lives in that same credential store. If your system has no usable credential store, Panopticon tells you what to do by hand and writes nothing.

Wrap records rotate daily and are retained for 30 days by default (`config.toml`).

## What never enters a container

Your home directory, your project files (only their *names* are replicated, as empty files), and your environment variables (replaced by decoys unless you explicitly pass them). The one permitted mount is `--self`, which mounts your MCP's source read-only so it can be built and observed.

## `--offline`

`--offline` disables registry lookups, the semantic analyzer, and every other outbound call. Cached registry data may still be read; when it's missing, results are reported `UNKNOWN` rather than guessed.
