# Getting started with Panopticon

This guide takes a first-time user from installation to one local MCP observation. It also maps the
rest of the command surface so the evidence can be repeated, compared, explained, and cleaned up.
Panopticon reports what was observed and what could not be observed; it does not replace your
judgment with a product verdict.

[Korean guide](getting-started.ko.md) · [Agent operating guide](agent-guide.md) ·
[Installation and release details](release.md) · [Privacy](privacy.md) ·
[Limitations](limitations.md)

## Before you start

| Task | Requirement |
|---|---|
| Discover configured MCPs with `doctor` | A supported client configuration: Claude Desktop, Claude Code, Cursor, VS Code, Windsurf, or an explicitly configured generic source |
| Observe a local MCP with `watch` | Docker or Podman running on Linux or macOS; use WSL2 for Linux observation behavior on Windows |
| Observe a remote MCP | Its HTTP/SSE endpoint and any headers you explicitly choose to provide; server-side files and processes remain `UNSUPPORTED` |
| Analyze an MCP repository with `scan` | A local source tree; standard/deep advisory lookup may use the network unless `--offline` is set |

The current public release is **1.0.2** across PyPI, npm, GitHub, and Homebrew.
`uv sync --all-extras` remains contributor setup, not an end-user installation method.

## 1. Choose one installation method

### Try once

```bash
uvx --from 'panopticon-mcp==1.0.2' pano version
uvx --from 'panopticon-mcp==1.0.2' pano doctor --offline
uvx --from 'panopticon-mcp==1.0.2' pano watch SERVER_NAME --offline
```

`uvx` creates a temporary tool environment for each invocation.
Use the full `uvx --from ... pano` prefix for every later command in this guide.

### Install persistently

Choose one owner for the installation:

```bash
uv tool install panopticon-mcp==1.0.2
# or
pipx install panopticon-mcp==1.0.2
# or
npm install --global @brnyxx/panopticon@1.0.2
# or
brew install brnyxx/homebrew-tap/panopticon
```

Verify it before observing anything:

```bash
pano version
```

The public release prints `pano 1.0.2 (schema 1.0)`. Native archive, checksum, Sigstore, air-gapped,
upgrade, and rollback instructions are in [the release guide](release.md).

Package installation contacts the selected package registry. `pano --offline` controls outbound
paths after Panopticon starts; it cannot retroactively make package installation offline.

## 2. Discover configured servers

Start with a read-only, offline inventory:

```bash
pano doctor --offline
```

For machine-readable output:

```bash
pano doctor --offline --json
```

`doctor` does not require Docker or Podman. It reports supported client discovery, installation
identities, configuration findings, exhaustive status, `reason_code`, and diagnostics. List the
client adapters without running checks with:

```bash
pano doctor --list-clients --offline
```

Choose a server name that actually appears in the output. `SERVER_NAME` in the examples is literal
placeholder text to replace; do not type shell angle brackets.
If two installations have the same name, `watch` returns `NAME_AMBIGUOUS`; it cannot select an
`installation_id`. Stop instead of guessing which entry to run.

## 3. Observe one server

Run one selected MCP in the decoy sandbox:

```bash
pano watch SERVER_NAME --offline
```

For an automation-friendly result and a local evidence card:

```bash
pano watch SERVER_NAME --offline --json --png
```

The default makes one call per discovered tool with a 20-second per-call timeout. Use `--calls` and
`--timeout` only when the target requires a different bounded run. Do not start with `--all`: one
selected server makes failures and evidence easier to attribute.

By default Panopticon does not pass the configured real environment values into the sandbox.
`--real-env`, `--real-env-all`, and `--allow-destructive` broaden what the target can receive or do;
use them only after reviewing the exact target and purpose. Values passed with the real-environment
options are rejected from persisted artifacts.

Offline local observation requires the digest-pinned sandbox image to be present already and does
not start the DNS/proxy egress observers. Network coverage therefore remains explicit rather than
being inferred from silence. Connected local observation records proxy/DNS attempts and can permit
proxied target traffic; read [the connected/offline boundary](privacy.md#connected-and-offline-observation)
before choosing it.

### Stage images for offline watch

On a clean runtime, make one separately authorized connection to GHCR before the offline
observation. This stages every immutable image that 1.0.2 can select without executing an MCP:

```bash
RUNTIME=docker  # or podman
$RUNTIME pull ghcr.io/brnyxx/pano-sandbox-base:0.1@sha256:0b88136f67f67f463ac1e9cc531dbe1bad7ea95d5ad5e4afd68337b966e24249
$RUNTIME pull ghcr.io/brnyxx/pano-sandbox-node:20@sha256:2ef58b44bd9ebc247e97d1b3c54f63570ae206b925b277d86d93e5319d1cd367
$RUNTIME pull ghcr.io/brnyxx/pano-sandbox-node:22@sha256:d0f7cc3fcac6a24ea0f8b7b9d62c542a04642ca5b38a4e249e017a7311a8b7c5
$RUNTIME pull ghcr.io/brnyxx/pano-sandbox-python:3.12@sha256:3e2b99433c18506f59d0e44e40b8af2b0350ee4df903252a1ab462f0eac3f589
```

The four pulls contact `ghcr.io`; `--offline` does not authorize or perform them. The digests are
the runtime trust values in `src/panopticon/sandbox/images.lock`. After they are local,
`watch --offline` neither pulls an image nor starts the connected DNS/proxy egress services.
If a required image is absent, startup stops with `IMAGE_NOT_PRESENT` before target execution.

## 4. Read the result correctly

A result combines stage status, stable `reason_code`, coverage dimensions, evidence, findings, and
diagnostics. Read them together.

| State | Meaning | Operator response |
|---|---|---|
| `COMPLETE` | The requested stage completed with the coverage it states | Review the evidence and declared scope; this is not a claim about unobserved future behavior |
| `PARTIAL` | Some requested work completed and some coverage is missing | Read coverage and diagnostics before drawing a conclusion |
| `INCOMPLETE` | Required work did not finish | Resolve the `reason_code`, then rerun the same bounded command |
| `FAILED` | The stage encountered a runtime failure | Inspect diagnostics and the runtime before retrying |
| `UNSUPPORTED` | The platform, mode, or target cannot provide that dimension | Keep the dimension unknown or choose a supported environment |
| `SKIPPED` | The stage was deliberately not run | Do not interpret it as evidence |
| `NOT_REQUESTED` | The command did not request the stage | Request it explicitly if it is required |
| `UNKNOWN` | Available evidence cannot support a conclusion | Preserve the uncertainty in reports and decisions |

Explain a finding by its stable rule ID:

```bash
pano explain WATCH-003
pano explain WATCH-003 --lang ko
```

## 5. Continue from a first observation

| Goal | Command | Notes |
|---|---|---|
| Save a comparison point | `pano baseline create --label first-observation` | Baselines address one installation and retain canonical evidence |
| List saved baselines | `pano baseline list` | Use `--json` for automation |
| Compare with a baseline | `pano diff SERVER_NAME --since auto` | Identical semantic input produces an empty diff |
| Analyze MCP source quickly | `pano scan . --mode quick --offline` | Static analysis without outbound product lookup |
| Include dependency advisories | `pano scan . --mode standard` | Sends exact locked package coordinates, not source, to OSV |
| Run the user-invoked semantic reviewer | `pano scan . --mode deep` | Shows the payload disclosure; sends redacted excerpts using the user's key |
| Run repository policy in CI | `pano ci . --mode standard --fail-on high` | Writes SARIF and applies the documented exit policy |
| Preview a configuration change | `pano fix SERVER_NAME --dry-run --offline` | Review the diff; applying requires a separate `--yes` invocation |
| Undo a recorded fix | `pano fix --undo TRANSACTION_ID` | Refuses when the file changed since the transaction |
| Wrap an installed MCP | `pano install CLIENT --dry-run` | Preserves the original command under `_pano_original`; apply only after review |
| Restore an installed wrapper | `pano uninstall CLIENT --dry-run` | Preview first, then use `--yes` after review |

## Exit codes for scripts and agents

| Code | Meaning |
|---:|---|
| `0` | Command completed without a policy or required-coverage exit condition |
| `1` | Policy findings met the selected failure threshold |
| `2` | Usage error |
| `3` | Required coverage is incomplete |
| `4` | Configuration error |
| `5` | Runtime failure or unsupported required runtime |
| `64` | Command surface reserved but not implemented in that build |

Do not rewrite a nonzero exit as success. Parse JSON `status`, `reason_code`, `coverage`, findings,
and diagnostics before deciding whether to retry, change environment, or stop.

## Local artifacts and cleanup

`~/.panopticon/` is created with mode `0700` and holds observations, baselines, wrap records, cache,
fix journals, and backups. Every persistence path canonicalizes and leak-checks its data first.
The `watch` terminal receipt prints `Artifact:` and JSON returns `artifact_path`; retain that path
because the product does not provide an observation-list command. The value is relative to
`~/.panopticon/`, normally `observations/...json`. When `--png` succeeds, read `observation_id`
from that JSON; the separate card is `~/.panopticon/cards/OBSERVATION_ID.png`.

Inspect and remove individual baselines with:

```bash
pano baseline list
pano baseline rm BASELINE_ID
```

Restore configuration changes before deleting their journals or backups. Panopticon has no bulk
data-deletion command; after active writers are stopped and configuration changes are restored,
remove selected retained artifacts with OS file tools or remove `~/.panopticon/` to clear all local
evidence and cache. The exact storage, outbound-path, and cleanup contract is in
[privacy.md](privacy.md).

## Troubleshooting

- **No server appears:** run `pano doctor --list-clients --offline`, confirm the intended client owns
  a configuration, and rerun `doctor` without selecting a different server by guesswork.
- **`RUNTIME_UNAVAILABLE`:** start Docker or Podman and rerun with `--runtime docker` or
  `--runtime podman` when explicit selection is needed.
- **`TIMEOUT`:** inspect the tool and target first; then use a bounded `--timeout` increase rather
  than an unbounded retry.
- **Remote file/process coverage is `UNSUPPORTED`:** that is the remote observation boundary, not a
  successful local observation.
- **A persisted artifact is rejected:** remove real token values, real home paths, or real-environment
  values from the requested persistence path; never disable the leak check.

## How the product is designed

The architecture separates CLI parsing, engine results, collectors, reporters, and the only
persistence gateway. Status and reason are typed at boundaries; reporters do not reinterpret them.
The sandbox receives a decoy home, not the user's home. The static demo uses local assets and a
deterministic bilingual builder with no browser analytics or storage.

Read [ARCHITECTURE.md](../ARCHITECTURE.md), [DESIGN.md](../DESIGN.md),
[the decision log](DECISIONS.md), and [the agent operating guide](agent-guide.md) for the contracts
behind those choices.
