# Operating Panopticon from an AI agent

This guide is for Claude Code, Codex, Cursor, Gemini CLI, and other automation agents that run
Panopticon for a user. It governs product operation, not contribution to the Panopticon repository;
repository contributors must also follow [`AGENTS.md`](../AGENTS.md).

Panopticon produces observation evidence. An agent must preserve statuses, reasons, coverage,
diagnostics, and uncertainty rather than converting them into a verdict.

## Default operating contract

After a user asks to inspect MCP configuration, an agent may run only the read-only discovery
defaults:

```bash
pano version
pano doctor --offline --json
```

`pano explain RULE_ID --json` is read-only and may follow when the user asks to interpret a reported
finding. `watch` is not read-only: it executes the selected third-party MCP. Run
`pano watch SERVER_NAME --offline --json` only when the user requested behavior observation or,
after discovery, explicitly authorized execution of that exact target.

The agent must replace `SERVER_NAME` only with an exact unambiguous name returned by `doctor`. It
must not infer a target from package popularity, select `--all`, or silently change to another
installation.

Package installation is a separate networked action. When `pano` is absent, report the exact pinned
installation command and the registry access it performs; run it only when the user's request
already authorizes installation.

```bash
uv tool install panopticon-mcp==1.0.1
```

The public version is 1.0.1. Do not present the forthcoming scoped npm package as an available 1.0.1
channel.

## Required sequence

### 1. Establish the installed product

Run `pano version`. Report the product and schema versions. If the command is absent, stop or perform
an already-authorized pinned installation; do not substitute an unpinned package.

### 2. Discover without broadening access

Run:

```bash
pano doctor --offline --json
```

Report:

- overall `status` and `reason_code`;
- diagnostics;
- detected clients;
- exact server and installation identifiers;
- configuration finding IDs;
- whether Docker or Podman is required for the requested next action.

A `3` exit with `INCOMPLETE` is not command success and not necessarily a process crash. Explain the
reason code and stop when the user must supply configuration or runtime context.

### 3. Bind one target

Use an exact server name from discovery. When several installations share a server identity, show
the installation choices rather than silently conflating them. The current CLI cannot select a
specific `installation_id`; a name collision returns `NAME_AMBIGUOUS`. Stop and report that
limitation rather than executing until the configured names are unambiguous.

### 4. Observe with narrow defaults

Confirm that the user's request authorizes behavior execution for this exact target, then run:

```bash
pano watch SERVER_NAME --offline --json
```

Local observation requires Docker or Podman. The user's home and working tree must not be mounted
into the target container. `--self` is the one explicit read-only source mount and applies only when
the user asks to observe the current MCP project.

Report each coverage dimension, observed evidence, stable finding IDs, status, reason code,
diagnostics, and persisted artifact paths. State clearly when a dimension is `UNSUPPORTED`,
`INCOMPLETE`, `SKIPPED`, `NOT_REQUESTED`, or `UNKNOWN`.

### 5. Explain before changing

Use `pano explain RULE_ID --json` or `--lang ko` to retrieve the six-section rule explanation.
Present the evidence, limits, and recommended action before proposing a change.

Configuration changes always follow preview, confirmation, backup, apply, re-check, and undo:

```bash
pano fix SERVER_NAME --dry-run --offline
```

Show the diff and the undo implications. `fix`, `install`, and `uninstall` are non-interactive:
`--yes` is their apply switch. Every apply requires separate explicit authorization for the exact
previewed mutating effect. Never edit a client MCP configuration directly as a shortcut.

## Actions that need separate explicit authorization

Do not infer approval for any of these from a general request to inspect an MCP:

- installing or upgrading a package, because the selected registry is contacted;
- staging a sandbox image with Docker or Podman, because `ghcr.io` is contacted;
- starting `pano watch` for one exact target;
- `pano watch --all`;
- `--real-env KEY1,KEY2` or `--real-env-all`;
- `--allow-destructive`;
- headers or credentials for a remote endpoint;
- `pano scan --mode deep`, which invokes the disclosed semantic network path;
- applying any `pano fix`, `pano install`, or `pano uninstall` preview by adding `--yes`;
- deleting `~/.panopticon/`, journals, backups, observations, or baselines;
- publishing or uploading an observation.

The tool itself has no observation-upload command. Do not add one through shell scripting or another
service unless the user separately specifies the exact destination and artifact.

## Prohibited shortcuts

An operating agent must never:

- describe `COMPLETE` as proof of future behavior;
- hide `UNKNOWN`, `INCOMPLETE`, `UNSUPPORTED`, `SKIPPED`, or `NOT_REQUESTED`;
- convert a nonzero exit into a pass;
- pass real environment values merely to make a target start;
- mount the user's home or project into the sandbox;
- disable leak checks or write raw traces outside approved persistence paths;
- apply a configuration change without the Panopticon dry-run and journal path;
- report a numeric risk score or certification-style conclusion;
- claim npm installation is public before registry evidence exists.

## Exit-code handling

| Code | Agent interpretation |
|---:|---|
| `0` | Parse and report the result; do not add a stronger conclusion |
| `1` | Policy threshold met; report finding IDs and evidence |
| `2` | Usage error; correct the invocation only when the intended arguments are unambiguous |
| `3` | Required coverage incomplete; report reason and missing coverage |
| `4` | Configuration error; do not modify configuration outside the documented change flow |
| `5` | Runtime failure or unsupported required runtime; report diagnostic and required environment |
| `64` | Command is unavailable in that build; do not fabricate equivalent output |

## Recommended response shape

Use this structure for every observation report:

```text
Target
- server_id: ...
- installation_id: ...
- client: ...

Run
- command: pano watch ... --offline --json
- exit_code: ...
- status: ...
- reason_code: ...

Coverage
- file: STATUS — reason — evidence or UNKNOWN
- net: STATUS — reason — evidence or UNKNOWN
- process: STATUS — reason — evidence or UNKNOWN
- snapshot: STATUS — reason — evidence or UNKNOWN

Findings
- RULE-ID — severity — evidence — declared source — limits

Artifacts
- observation: ~/.panopticon/...
- optional PNG/SARIF/baseline: ...

Unobserved or blocked
- explicit missing dimensions and diagnostics

Operator action
- one bounded next command, or the exact user decision required
```

Do not include raw secret values, real home absolute paths, or values supplied with real-environment
options in the response.

## Copyable agent instruction

A user can paste this into an agent session:

```text
Use Panopticon to inspect one MCP. Do not install packages unless this request already authorizes the
pinned public release. Start with `pano version` and `pano doctor --offline --json`. Show me the exact
server names and installation identities; do not select `--all`. After I identify one target, run
`pano watch SERVER_NAME --offline --json`; stop on `NAME_AMBIGUOUS` because the CLI cannot bind an
installation ID. Do not use real environment values, destructive calls, remote credentials, deep
semantic analysis, or apply any configuration preview without separate explicit authorization.
Report exit code, status, reason_code, every coverage dimension, finding IDs, diagnostics, artifact
paths, and all unknown or unsupported areas. Do not turn the evidence into a product verdict.
Preview every configuration change with `pano fix ... --dry-run --offline`, show the diff, and
preserve the undo path.
```

## Source and design references

- Human first-use flow: [getting-started.md](getting-started.md)
- Storage and outbound paths: [privacy.md](privacy.md)
- Observation limits: [limitations.md](limitations.md)
- Runtime architecture: [ARCHITECTURE.md](../ARCHITECTURE.md)
- Demo design system: [DESIGN.md](../DESIGN.md)
- Frozen product decisions: [DECISIONS.md](DECISIONS.md)
