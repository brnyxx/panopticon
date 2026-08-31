<div align="center">

<img src="https://raw.githubusercontent.com/brnyxx/panopticon/main/.github/assets/logo.svg" alt="Panopticon logo: a panopticon floor plan drawn as an eye, one cell lit in orange" width="96"/>

<img src="https://raw.githubusercontent.com/brnyxx/panopticon/main/.github/assets/hero.svg" alt="Panopticon — We don't watch you. We watch your MCPs. A local-first MCP behavior observatory." width="920"/>

[![Version](https://img.shields.io/badge/version-1.0.1-orange?style=flat-square&labelColor=0A0E1A)](https://github.com/brnyxx/panopticon/blob/main/docs/release.md) [![Python](https://img.shields.io/badge/python-3.11%2B-4B8BBE?style=flat-square&labelColor=0A0E1A)](https://github.com/brnyxx/panopticon/blob/main/pyproject.toml) [![License](https://img.shields.io/badge/license-MIT-E8EDF7?style=flat-square&labelColor=0A0E1A)](https://github.com/brnyxx/panopticon/blob/main/LICENSE) [![No telemetry](https://img.shields.io/badge/telemetry-none-2EA043?style=flat-square&labelColor=0A0E1A)](https://github.com/brnyxx/panopticon/blob/main/docs/privacy.md)

[한국어 안내](https://github.com/brnyxx/panopticon/blob/main/docs/README.ko.md)

</div>

`pano` finds MCP servers configured in your AI clients, runs a selected server in a decoy-filled
sandbox, and records files, network hosts, processes, and declared-versus-observed differences.
It reports observation evidence; it does not make a verdict for you.

<div align="center">
<img src="https://raw.githubusercontent.com/brnyxx/panopticon/main/.github/assets/panopticon.png" alt="An inspection tower at the centre of a ring of cells, each holding an MCP server" width="860"/>
</div>

## Start here

Install the current public PyPI release, inspect the configured server names, and observe one
selected server:

```bash
uv tool install panopticon-mcp==1.0.1
pano doctor --offline
pano watch SERVER_NAME --offline
```

The checked-out repository is unpublished 1.0.2 development. `uv sync --all-extras` is contributor
setup, not a public installation path.

Replace `SERVER_NAME` with a name printed by `doctor`; it is literal text rather than shell angle
brackets. Package installation contacts the selected registry before `pano` runs. `--offline`
then disables Panopticon's registry, advisory, package-lookup, and semantic-analyzer outbound
paths. Traffic attempted by the selected MCP remains sandbox evidence rather than a Panopticon
product lookup. `doctor` does not require Docker or Podman; local `watch` does.
On a clean runtime, follow [Stage images for offline watch](docs/getting-started.md#stage-images-for-offline-watch)
before the first offline observation.

For a one-time version check, `uvx --from 'panopticon-mcp==1.0.1' pano version` prints
`pano 1.0.1 (schema 1.0)`. Other installation methods, upgrades, rollback, and air-gapped use are
in the [installation and release guide](https://github.com/brnyxx/panopticon/blob/main/docs/release.md).

The bilingual demo source starts at
[`site/template.html`](site/template.html). `scripts/build_site.py` validates locale parity and
builds both routes deterministically; the SHA-pinned Pages workflow deploys those generated
artifacts from `main`. The page has no analytics, cookies, local storage, or runtime remote
resources. Requests handled by GitHub Pages remain subject to GitHub's hosting policy.

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

## Read the result

- `COMPLETE` means the stage completed with its stated coverage.
- `UNKNOWN` means the available evidence cannot support a conclusion.
- `INCOMPLETE` means the requested observation did not complete all needed work.
- `UNSUPPORTED` means that dimension is unavailable for this platform, mode, or target.

These states are not interchangeable. For example, remote observation cannot see server-side file
or process activity and marks those dimensions `UNSUPPORTED`. A rule ID such as `WATCH-003`,
`CFG-008`, or `HIST-002` identifies the exact check; read its bilingual explanation with:

```bash
pano explain WATCH-003
```

Review the evidence card and the terminal result together. It intentionally retains visible
coverage and rule identifiers rather than converting missing observation into a reassuring result.

## How it is designed

- `cli` parses and renders; `engine` owns typed outcomes and exit policy.
- Collectors return exhaustive status, stable `reason_code`, coverage, evidence, and diagnostics.
- The sandbox receives a generated decoy home, never the user's home. `--self` is the one explicit
  read-only project-source mount.
- `store` is the only artifact writer and performs canonicalization, leak checking, and atomic
  replacement before persistence.
- The demo is built from bilingual locale catalogs with a deterministic standard-library builder
  and local browser assets only.

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
