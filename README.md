<div align="center">

<img src="https://raw.githubusercontent.com/brnyxx/panopticon/main/.github/assets/logo.svg" alt="Panopticon aperture mark: one selected orange segment, one observation ring, and a terminal-cursor pupil" width="96"/>

<img src="https://raw.githubusercontent.com/brnyxx/panopticon/main/.github/assets/hero.svg" alt="Panopticon flow: select one MCP, run it in a generated decoy environment, and inspect the resulting evidence record" width="920"/>

[![Version](https://img.shields.io/badge/version-1.0.1-orange?style=flat-square&labelColor=0A0E1A)](https://github.com/brnyxx/panopticon/blob/main/docs/release.md) [![Python](https://img.shields.io/badge/python-3.11%2B-4B8BBE?style=flat-square&labelColor=0A0E1A)](https://github.com/brnyxx/panopticon/blob/main/pyproject.toml) [![License](https://img.shields.io/badge/license-MIT-E8EDF7?style=flat-square&labelColor=0A0E1A)](https://github.com/brnyxx/panopticon/blob/main/LICENSE) [![No telemetry](https://img.shields.io/badge/telemetry-none-2EA043?style=flat-square&labelColor=0A0E1A)](https://github.com/brnyxx/panopticon/blob/main/docs/privacy.md)

[한국어 안내](https://github.com/brnyxx/panopticon/blob/main/docs/README.ko.md)

</div>

`pano` finds MCP servers configured in your AI clients, runs a selected server in a decoy-filled
sandbox, and records files, network hosts, processes, and declared-versus-observed differences.
It reports observation evidence; it does not make a verdict for you.

**[Explore the bilingual interactive product tour](https://brnyxx.github.io/panopticon/)** — a
static, local-asset demonstration with no analytics, cookies, browser storage, or automatic remote
runtime requests.

## Start here

Install the current public PyPI release, inspect the configured server names, and observe one
selected server:

```bash
uv tool install panopticon-mcp==1.0.1
pano doctor --offline
pano watch SERVER_NAME --offline
```

What happens:

1. `doctor` lists configured names without starting third-party code or requiring Docker/Podman.
2. You replace `SERVER_NAME` with one exact printed name. Panopticon never guesses through
   `NAME_AMBIGUOUS`.
3. After separate execution approval, `watch` runs that MCP in a generated decoy home and records
   its file, network, process, leak, and snapshot evidence.
4. The receipt preserves status, `reason_code`, every coverage dimension, finding IDs, and the
   artifact path. Missing evidence remains visible.

Before the first observation:

- Package installation contacts the selected registry before `pano` runs. `--offline` then
  disables Panopticon registry, advisory, package-lookup, and semantic-analyzer outbound paths.
- Traffic attempted by the selected MCP remains sandbox evidence, not a Panopticon product lookup.
- Local `watch` needs Docker or Podman. A clean runtime also needs the
  [digest-pinned images staged](docs/getting-started.md#stage-images-for-offline-watch).
- The checkout is unpublished 1.0.2 development. `uv sync --all-extras` is contributor setup, not
  a public installation path.

For a one-time version check, `uvx --from 'panopticon-mcp==1.0.1' pano version` prints
`pano 1.0.1 (schema 1.0)`. Other installation methods, upgrades, rollback, and air-gapped use are
in the [installation and release guide](https://github.com/brnyxx/panopticon/blob/main/docs/release.md).

## Read the record

- `COMPLETE` means one named dimension completed with its stated coverage.
- `UNKNOWN` means the available evidence cannot support a conclusion.
- `INCOMPLETE` means the requested observation did not complete all needed work.
- `UNSUPPORTED` means that dimension is unavailable for this platform, mode, or target.

These states are not interchangeable. `WATCH-001`, for example, identifies a decoy marker that
reached an outbound sink; the marker value is never displayed. Inspect its bilingual rule document
with `pano explain WATCH-001`.

<div align="center">
<img src="https://raw.githubusercontent.com/brnyxx/panopticon/main/.github/assets/evidence-card.png" alt="Illustrative Panopticon reporter output with incomplete overall coverage, complete file and network stages, unsupported process tracing, one WATCH-001 finding, and one leak finding" width="720"/>
</div>

<p align="center"><sub>Illustrative fixture rendered by Panopticon's deterministic PNG reporter. It is evidence, not a verdict.</sub></p>

## Pick the right workflow

| You want to… | Start with… | Requirement or boundary |
|---|---|---|
| Find configured MCPs | `pano doctor --offline` | No container runtime required |
| Observe one local MCP | `pano watch SERVER_NAME --offline` | Docker or Podman; use an exact name from `doctor` |
| Explain one finding | `pano explain RULE_ID` | English by default; add `--lang ko` for Korean |
| Compare repeated observations | `pano baseline create` then `pano diff SERVER_NAME` | Baselines retain canonical evidence for one installation |
| Analyze an MCP repository | `pano scan . --mode quick --offline` | Standard/deep add advisory or semantic paths described in privacy docs |
| Apply repository policy | `pano ci . --mode standard --fail-on high` | Writes SARIF and uses documented exit-code precedence |
| Change a client configuration | `pano fix SERVER_NAME --dry-run --offline` | Review the diff before a separate `--yes` invocation |
| Wrap or restore an MCP command | `pano install CLIENT --dry-run` / `pano uninstall CLIENT --dry-run` | Original command is retained for undo |

The complete first-use flow, installation matrix, status table, exit codes, artifact locations,
cleanup, troubleshooting, and command examples are in
**[Getting started](docs/getting-started.md)**.

## Use Panopticon from an AI agent

Agents should consume JSON and preserve uncertainty instead of summarizing every nonzero exit as a
failure or every completed stage as a verdict. The narrow default sequence is:

```bash
pano version
pano doctor --offline --json
pano watch SERVER_NAME --offline --json
```

An agent must not choose `--all`, pass real environment values, allow destructive calls, run deep
semantic analysis, apply `--yes`, or delete local evidence without separate explicit authorization.
The copyable operating prompt, response schema, exit-code policy, and confirmation boundaries are
in **[Operating Panopticon from an AI agent](docs/agent-guide.md)**.

## How it is designed

- Typed collectors preserve exhaustive status, stable `reason_code`, coverage, evidence, and
  diagnostics through one engine-owned exit policy.
- The sandbox receives a generated decoy home, never the user's home; `store` canonicalizes,
  leak-checks, and atomically replaces every persisted artifact.
- The bilingual demo is deterministic and loads only repository-owned browser assets.

Read [the architecture](ARCHITECTURE.md), [the demo design system](DESIGN.md),
[the frozen decisions](docs/DECISIONS.md), and [the product build plan](panopticon-buildplan.md)
for the complete contracts.

## Privacy and cleanup

Read the complete [privacy and outbound-traffic table](https://github.com/brnyxx/panopticon/blob/main/docs/privacy.md)
before observation, especially before allowing real environment values or running
`scan --mode deep`. `--offline` disables Panopticon's outbound product paths, but package
installation uses the selected package registry before `pano` runs. Artifacts are leak-checked
before persistence. Standard/deep scan sends exact locked package coordinates—not source—to OSV
for advisory lookup. Storage, record retention, configuration undo, and package rollback are
covered in the [release guide](https://github.com/brnyxx/panopticon/blob/main/docs/release.md) and
[limitations](https://github.com/brnyxx/panopticon/blob/main/docs/limitations.md).

## Lineage

The static, semantic, and dependency analysis assets in `scan` come from
[MCP-Sentinel](https://github.com/BashaarJavaid/MCP-Sentinel) at commit
[e717e955](https://github.com/BashaarJavaid/MCP-Sentinel/commit/e717e955210b1d2a3e9fb1cdc266587c77ffebf3)
(MIT). The exact carried file list is in
[THIRD_PARTY_NOTICES.md](https://github.com/brnyxx/panopticon/blob/main/THIRD_PARTY_NOTICES.md).

MIT.
