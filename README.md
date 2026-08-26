# Panopticon

> **We don't watch you. We watch your MCPs.**

`pano` finds the MCP servers installed in your AI clients, runs them inside a decoy-filled sandbox, and shows you what they *actually* did — file by file, host by host, per tool call — against what they *claim* to do.

```
$ pano watch github

Ran github MCP in an isolated sandbox and called 3 tools. (14s)

list_issues
  READ   ~/.gitconfig
  READ   ~/.ssh/config                        not declared
  NET    api.github.com:443
  NET    collector.example-telemetry.io:443    not in docs
  LEAK   AWS_ACCESS_KEY_ID sent to host above  <- decoy value

Declared   repo read/write (README, tool descriptions)
Observed   2 files · 2 hosts · 1 decoy leak

Verdict    2 undeclared behaviors, 1 leak
           details: pano explain WATCH-003 WATCH-007
```

## Install

```bash
uvx panopticon-mcp doctor        # discovery + config checks, no Docker needed
uvx panopticon-mcp watch --all   # needs Docker or Podman
```

## Principles

1. Observation before judgment — we report what happened; you decide.
2. Unknown is visible — nothing unobserved is called safe.
3. Your home never enters a container — decoys only, no uploads, no telemetry.

## Status

Pre-alpha scaffold. Implementation follows [`docs/PLAN.md`](docs/PLAN.md) epic by epic; progress in [`docs/PROGRESS.md`](docs/PROGRESS.md). Agents: read [`AGENTS.md`](AGENTS.md).

## Lineage

Static, semantic, and dynamic analysis in the `scan` line are inherited from [MCP-Sentinel](https://github.com/BashaarJavaid/MCP-Sentinel) (MIT). See `NOTICE`.

## License

MIT.
