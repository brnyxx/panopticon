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

Choose **one** installation method. For a one-time run, use `uvx`:

```bash
uvx panopticon-mcp@1.0.1 version
uvx panopticon-mcp@1.0.1 doctor
```

The first command verifies the installed release (`pano 1.0.1 (schema 1.0)`). The second lists
discoverable MCP configuration and checks it without Docker or Podman. Persistent installs
(`uv tool`, `pipx`, Homebrew, or a native archive), upgrades, rollback, and air-gapped use are in
the [installation and release guide](https://github.com/brnyxx/panopticon/blob/main/docs/release.md).

Pick one server name from `doctor`, then observe it:

```bash
pano watch SERVER_NAME --png
```

Local observation requires Docker or Podman. `--png` creates a deterministic, leak-checked PNG
evidence card alongside the stored observation. Do not treat this example as captured output:
your result names the selected server, its coverage, and its observed evidence.

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
