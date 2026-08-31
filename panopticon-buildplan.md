# Panopticon — v1.0.0 Implementation Plan

> **We don't watch you. We watch your MCPs.**
> A local-first tool that discovers installed MCP servers, runs them in a decoy-filled sandbox, records what they actually do, and explains the gap between declared and observed behavior.

| Item | Value |
|---|---|
| Product | Panopticon |
| CLI | `pano` |
| PyPI | `panopticon-mcp` |
| npm | `@brnyxx/panopticon` |
| Document type | Complete v1.0.0 plan plus accepted post-1.0 hardening — no timelines, definition-of-done driven |
| Upstream | `BashaarJavaid/MCP-Sentinel` @ pinned commit `e717e955` (MIT) — static/semantic/dependency analysis assets vendored into the `scan` line with per-file provenance and checksums |
| Repository | `brnyxx/panopticon` |
| Images | `ghcr.io/brnyxx/pano-sandbox-*`, trusted by digest |

---

## 0. How this document is organized

This document defines **everything that must exist in v1.0.0**. There are no weeks or deadlines. Each implementation unit (Epic) has scope, contracts, tests, and a definition of done; epics only carry a dependency order. An agent closes epics in that order.

- §1 Product definition and scope
- §2 v1.0.0 definition of done (master checklist)
- §3 Epic list and dependency graph
- §4–§19 Epic details for E01–E16
- §20 Complete rule catalog
- §21 Data schemas
- §22 Quality, security, documentation standards
- §23 Version stages
- §24 Open decisions
- §25 Product description
- §26–§28 Epic details for E17 (reporters), E18 (i18n), E19 (release)
- §29 E20 post-1.0 npm distribution and production hardening

Precedence, highest first: an accepted entry in `docs/DECISIONS.md` overrides this document; this document overrides the prose of any execution plan. Execution ordering and evidence live in the execution plan `.omo/plans/panopticon-v1-completion.md`, held outside version control and cited by the `Plan:` footer of every commit; it sequences the work but never redefines a contract. A conflict at any level is amended in the authoritative source before work continues, in the same change that found it.

---

## 1. Product definition and scope

### 1.1 One sentence

Automatically discover MCP servers installed in AI clients, invoke them for real inside a decoy-filled isolated environment, record file/network/process/leak behavior per tool call, explain the gap against the declared scope, and optionally keep recording continuously.

### 1.2 Two product lines

| Line | Commands | Users | Origin |
|---|---|---|---|
| **Observe line** | `doctor`, `watch`, `wrap`, `install`, `fix`, `diff`, `explain`, `badge` | People who install MCPs; platform engineers | New |
| **Analyze line** | `scan` (quick/standard/deep), `ci` | MCP server authors | Vendored from upstream `e717e955` |

Both lines share one CLI, one finding model, and one set of reporters. The observe line is the face of the product; the analyze line reinforces it via `watch --self` and CI.

### 1.3 In scope for v1.0.0

- Config discovery for 6 clients (Claude Desktop, Claude Code, Cursor, VS Code, Windsurf, generic)
- Isolated observation of stdio MCPs (Docker/Podman); observation of HTTP/SSE remote MCPs via a logging proxy
- Decoy home, decoy environment variables, leak detection
- Declared-scope extraction and declared-vs-observed comparison
- Full config, behavior, history, and fix rule sets
- Continuous wrapper (`wrap`) and client injection (`install`)
- Baseline and diff, including implicit baseline
- Korean and English remediation
- terminal / JSON / SARIF / Markdown / PNG reporters, SVG badge
- Upstream static/semantic/dynamic analysis (`scan`) stabilized, GitHub Action
- macOS and Linux official; Windows via WSL2 official, native Windows discovery only
- Single-binary distribution in addition to `uvx`
- A typed core spine before feature work: branded identities, immutable persistence-boundary models, structured stage results, one persistence gateway, `SecretStore`, and explicit engine pipelines (§4, `ARCHITECTURE.md`)
- Dual-era MCP support: current `2026-07-28` per-request metadata plus the legacy `initialize` handshake, Streamable HTTP plus deprecated HTTP+SSE fallback (§11, §12, DECISIONS #11)

### 1.4 Explicitly out of scope for v1.0.0

- Public observatory, public catalog, weekly reports (only an export format is defined)
- Universal safety score, "Safe/Certified" certification
- Exploitation of external services
- Telemetry of any kind (not even opt-in)
- Accounts, SaaS, organization dashboard
- Native Windows sandbox
- Automatic addition/removal of MCP entries
- Any post-1.0 roadmap item (`ROADMAP.md`)

### 1.5 Product principles

1. Observation precedes judgment. We report what a server *did*; the user decides whether it is dangerous.
2. What was not observed is never called safe. `UNKNOWN` is always printed.
3. The user's home and credentials never enter a container.
4. Every persisted file must pass the leak check.
5. Same input, same output. Diff is deterministic.
6. Fix is always: diff → confirm → backup → apply → re-check → undo available.
7. Korean and English share rule IDs, evidence, and structure.
8. We don't watch the user. Network use is limited to the exhaustive paths in `docs/privacy.md`: registry/package-install lookups, exact-version OSV advisory queries in standard/deep scan, the MCP's sandbox traffic, explicitly permitted remote observation, bounded FIX-008 validation, and the user-invoked semantic analyzer in `scan --mode deep`. `--offline` disables every path.
9. Identity is explicit: `server_id` groups, `installation_id` addresses one config entry, `logical_key` addresses one finding across runs.
10. State is structured: every stage carries an exhaustive status, a stable `reason_code`, and explicit coverage dimensions.

---

## 2. v1.0.0 definition of done

v1.0.0 exists when all of the following hold. Any gap keeps the version at 0.x.

### Contracts
- [ ] Typed core spine in place: branded IDs, immutable persistence-boundary models, exhaustive stage status/reason/coverage, and explicit engine pipelines (§4).
- [ ] `installation_id` distinct from `server_id`; `logical_key` distinct from occurrence id (§6, §14).
- [ ] One persistence, canonicalization, and leak-check gateway, enforced by a checker (§4, §21).
- [ ] `SecretStore` backed by the OS credential store, authenticated encryption for secret-bearing backups, guidance-only fallback (§16).
- [ ] Dual-era MCP support with recorded requested version, selected version, era, and fallback reason (§11, §12).

### Features
- [ ] Read-only discovery and parsing of 6 client configs, producing an inventory.
- [ ] Isolated execution of stdio MCPs with per-tool file/network/process/leak events.
- [ ] Remote HTTP/SSE MCPs invoked through a logging proxy with network/leak events.
- [ ] Declared scope extracted from 5 sources and compared against observations, producing every WATCH rule.
- [ ] All CFG, HIST, WATCH, FIX, SENT rules implemented, each with fixture tests.
- [ ] `fix` performs every FIX rule with dry-run, backup, and undo.
- [ ] `wrap` relays stdio with ≤1 ms added latency and records per-tool network events.
- [ ] `install`/`uninstall` injects/removes wrap for all 6 clients.
- [ ] Explicit and implicit baselines and diff work; identical input yields zero diff.
- [ ] `scan` quick/standard/deep work; upstream replay demo reproduces `COMPLETE`.
- [ ] GitHub Action uploads SARIF in quick/standard modes.
- [ ] terminal/JSON/SARIF/Markdown/PNG reporters and SVG badge exist.
- [ ] Every rule has a ko/en 6-section explain document.

### Quality
- [ ] Test coverage ≥ 85%; upstream's 125 tests kept green.
- [ ] Every one of the 20+ leak fixtures rejected by every persist sink, in raw, escaped, URL-encoded, form-encoded, base64, and chunk-split variants.
- [ ] Exact expected findings on 5 evil and 5 clean fixture MCPs.
- [ ] CI matrix green: macOS (arm64, x86_64), Linux (x86_64, arm64), native Windows discovery, WSL2 sandbox. Native Windows and WSL2 are distinct gates.
- [ ] On a clean machine: `pano doctor` first result ≤ 5 min; `pano watch <mcp>` first result ≤ 3 min (including image pull).
- [ ] Repeat-run semantic zero diff and stable reporter hashes on fixed fixtures.

### Distribution and docs
- [ ] `uvx panopticon-mcp`, `pipx`, Homebrew tap (`brnyxx/homebrew-tap`), 4 GitHub Release binaries, signed sandbox images under `ghcr.io/brnyxx`.
- [ ] README ko/en, architecture, rule catalog, limitations, privacy, SECURITY.md, disclosure policy, THIRD_PARTY_NOTICES.md.
- [ ] Schema version `1.0` frozen exactly once at the 0.9 gate; idempotent migrators from every shipped 0.x version provided.
- [ ] Artifacts built once and promoted; a partial publication resumes the remaining channels with the same immutable artifacts and never reuses a version.

---

## 3. Epic list and dependency graph

| ID | Epic | Depends on |
|---|---|---|
| E01 | Project foundation (repo, packaging, CI, schemas) | — |
| E02 | Discovery (client config detection) | E01 |
| E03 | Inventory & identity | E02 |
| E04 | Registry history (npm/PyPI/GitHub) | E03 |
| E05 | Sandbox runtime (containers, images, network isolation) | E01 |
| E06 | Decoy system | E05 |
| E07 | Event collection (strace, DNS, proxy, snapshot) | E05, E06 |
| E08 | Probe (MCP client, arg generation, call driver) | E05 |
| E09 | Remote MCP observation (HTTP/SSE) | E07, E08 |
| E10 | Declared-scope extraction | E03, E04 |
| E11 | Finding model and rule engine | E01 |
| E12 | Rule implementation (CFG, HIST, WATCH) | E03, E04, E07, E10, E11 |
| E13 | Fix (auto-remediation, backup, undo) | E12 |
| E14 | Baseline & diff | E11, E03 |
| E15 | Wrap & install | E03, E07 (partial), E11 |
| E16 | Analyze line (upstream scan stabilization, CI) | E01, E11 |
| E17 | Reporters (terminal, JSON, SARIF, Markdown, PNG, badge) | E11 |
| E18 | i18n (rule docs, glossary, explain) | E12 |
| E19 | Distribution, docs, security verification, release | all |
| E20 | npm native distribution and production hardening | E19 |

The discovery branch (E02–E04) and the observation-engine branch (E05–E08) can proceed in parallel; they merge at E12.

---

## 4. E01 — Project foundation and core spine

### Scope
- Pinned upstream provenance, not forked history. `THIRD_PARTY_NOTICES.md` lists the MIT copyright, the pinned commit `e717e955`, a summary of changes, and every vendored file with its checksum (DECISIONS #13).
- `pyproject.toml`: Python 3.11+, `uv` lock, entry point `pano`, package `panopticon-mcp`, project URLs pointing at `brnyxx/panopticon`.
- Directory layout as in `AGENTS.md`.
- CI: ruff, ruff-format, mypy (strict), pytest with coverage, schema validation, i18n parity, leak fixtures, the direct-write checker, and the 250-pure-LOC audit. OS matrix expanded in E19.
- Logging: structured (`structlog`), stderr by default, `PANO_LOG=json`. Log records also pass `leak_check`.
- Config: `~/.panopticon/config.toml` (proxy, container runtime, extra allowlist, language) for the user; `panopticon.toml` at an MCP repo root for the analyze line (scan modes, fail policy, suppressions, inline declaration). Precedence: CLI flag > `PANO_*` env > file.

#### Typed core spine
- `models/`: branded ID types, immutable Pydantic v2 persistence-boundary models, diagnostics, protocol era, requested and selected versions, discovery and fallback reasons, schema metadata. No raw dictionary crosses a boundary and no nested record may be partially populated.
- Identity: group-level `server_id` (§6) plus `installation_id = hash(client | normalized config path | scope | JSON pointer | entry name)`. Spans carry `span_id = tool + call_index`. Baselines are self-contained immutable snapshots.
- State: exhaustive `COMPLETE | PARTIAL | INCOMPLETE | FAILED | UNSUPPORTED | SKIPPED | NOT_REQUESTED` with a stable `reason_code` and per-dimension coverage (file, net, process, dns, proxy, snapshot, stdio). Modern version discovery is its own stage; the legacy-only handshake is `NOT_REQUESTED` for a modern run.
- Schemas: `0.1` development line, generated and validated from the runtime models, with explicitly dispatched idempotent migrators. `1.0` is frozen only at the 0.9 gate (§21, §23, DECISIONS #6).

#### Persistence gateway
- `store/` plus `util/canonicalize.py` are the only persist path: typed normalization → versioned canonical serialization → mandatory `LeakContext` scan → restrictive same-directory temp write → flush and fsync → symlink-safe atomic replace → directory fsync where supported. This covers every cache, observation, baseline, finding, wrap record, alert, journal entry, backup, log artifact, and every JSON, SARIF, Markdown, PNG, and SVG output.
- Leak matching covers raw, escaped, URL-encoded, form-encoded, base64, and chunk-boundary variants plus native and WSL home paths. Render models are sanitized before binary compression.
- An AST checker forbids direct persistence outside `store/` and the approved config-patch modules.

#### Secrets
- `SecretStore` protocol with macOS Keychain, Linux Secret Service, and native Windows Credential Manager backends and a deterministic in-memory fake. Encryption keys live in the credential store; secret-bearing config backups use authenticated encryption. With no available backend the result is typed guidance-only and nothing is written (DECISIONS #10).

#### Engine and CLI boundaries
- `engine/` holds pipeline contracts for doctor, watch, diff, and scan without feature implementation, plus the boundary `Result` and diagnostics types.
- One exit-code table with defined precedence over success, policy findings, incomplete required stages, runtime errors, config errors, and usage errors. `cli/` parses and renders only.
- Expected rule and i18n manifests exist so a registry with zero rules cannot pass vacuously.

### Definition of done
- `uv run pano version` works. Round-trip tests for all schemas (§21) pass on the `0.1` line, including invalid-input rejection and migration replay. Identity, state-semantics, and persistence-gateway suites pass, including at least 20 leak classes across every sink. `SecretStore` capability probes, key rotation, tamper rejection, and unavailable-backend guidance pass. Engine and reporter protocols type-check, the exit-code table is covered, and the zero-rule manifest fails until expected scope is staged. The direct-write checker reports zero violations. All CI jobs green. Upstream's 125 tests are E16's gate, not E01's.

---

## 5. E02 — Discovery

### Supported clients and paths

| client | macOS | Linux | Windows (incl. WSL2) | format |
|---|---|---|---|---|
| claude-desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` | `~/.config/Claude/claude_desktop_config.json` | `%APPDATA%\Claude\claude_desktop_config.json` | `mcpServers` |
| claude-code | `~/.claude.json` (global `mcpServers`, `projects[<path>].mcpServers`), cwd `.mcp.json` | same | same | `mcpServers`, `type: stdio/http/sse` |
| cursor | `~/.cursor/mcp.json`, cwd `.cursor/mcp.json` | same | `%USERPROFILE%\.cursor\mcp.json` | `mcpServers` |
| vscode | cwd `.vscode/mcp.json`, user `settings.json` → `mcp.servers` | same | same | `servers`, `${input:*}` variables |
| windsurf | `~/.codeium/windsurf/mcp_config.json` | same | same | `mcpServers` |
| generic | `--config <path>` | | | `mcpServers` or `servers` |

### Contract
```python
class ClientAdapter(Protocol):
    name: str

    def candidate_paths(self, env: DiscoveryEnv) -> list[Path]: ...
    def parse(self, path: Path) -> ParseResult: ...  # entries | ParseError(reason, line)
    def write(
        self, path: Path, entries: list[RawServerEntry]
    ) -> None: ...  # used only by fix/install
```
- `DiscoveryEnv` encapsulates home, cwd, os, env so tests can inject.
- Distinguish `NOT_FOUND` / `PARSE_ERROR` / `PERMISSION`.
- Follow symlinks but record realpath. Project-scoped configs are searched at most 3 parent levels above cwd.
- Accept JSONC (comments, trailing commas). VS Code `${input:id}`, `${env:VAR}`, `${workspaceFolder}` are kept as unresolved variables; never guess values.
- Recognize disabled flags (`disabled: true`, `enabled: false`).

### Tests
- Per-client fixtures: clean, secret, broad_fs, duplicate, malformed, disabled, remote, variables — 40+ total.
- mtime/hash test proving real configs are never modified.

### Definition of done
- All 6 adapters pass fixtures. `pano doctor --list-clients` prints discovery status as a table.

---

## 6. E03 — Inventory & identity

### `InstalledServer` normalization
- Fields: server_id, name, client, config_path, scope (global/project), transport, command, args, env_keys, url (remote), headers_keys (remote), package, source, pinned, resolved, identity_confidence, disabled, wrapped.
- One config entry → one `InstalledServer`. No merging; reporters group by server_id only.

### server_id rules
```
npm:<package>                 npx / node <node_modules path> / bunx
pypi:<package>                uvx / pipx run / python -m
github:<owner>/<repo>         source directory whose git remote is GitHub
docker:<image>                docker run <image>
remote:<host>[/<path>]        http/sse URL
local:<sha256(command+args)[:12]>   everything else
```

### installation_id rules
`installation_id = hash(client | normalized config path | scope | JSON pointer | entry name)`.

- `server_id` is the **group** identity: it answers "which package is this". `installation_id` is the **entry** identity: it answers "which config entry is this".
- The same package installed in three clients yields one `server_id` and three `installation_id` values. Entries are never merged.
- Observations, baselines, wrap records, suppressions, fix plans, and diff joins all key on `installation_id`. Reporters group by `server_id`. Registry history and the deterministic argument seed use `server_id`.
- `identity_confidence: low` (local commands) never merges by `server_id` and never compares across entries.
- Package-name extraction follows fixed parser rules: `npx [-y] [--package=X] <pkg>[@ver] [args]`, `uvx [--from X] <pkg>`, `node <path>` → `node_modules/<pkg>/`, `python -m <mod>` → reverse-map module to PyPI name via registry (low confidence on failure).
- identity_confidence: high (registry confirmed) / medium (shape matches, unconfirmed) / low (local). `low` is never merged or compared.
- `resolved` version read from npx cache (`~/.npm/_npx/*/node_modules/<pkg>/package.json`) or uv cache; null if absent.

### Definition of done
- 30 arg-parsing fixtures (compound flags, scoped packages, version tags, env substitution) produce expected server_ids. Duplicate-install fixtures group without merging.

---

## 7. E04 — Registry history

### Scope
- npm: `https://registry.npmjs.org/<pkg>` → `time`, `dist-tags`, `maintainers`, `repository`, `dist.integrity`. Cache responses and compare maintainers with the previous cache.
- PyPI: `https://pypi.org/pypi/<pkg>/json` → `releases` (upload_time), `info.project_urls`, `info.author`.
- GitHub: `repos/<owner>/<repo>` (archived, pushed_at, default_branch), `releases`, `tags`. Respect unauthenticated rate limits; use `GITHUB_TOKEN` if present (value is leak-checked).
- Cache: `~/.panopticon/cache/registry/<ecosystem>/<pkg>.json`, TTL 24h, ETag. `--offline` uses cache only.

### Output
- `PackageHistory`: releases[(version, published_at)], latest, maintainers, repository_url, archived.
- `since(ts)` → release count, major jumps, maintainer changed.

### Definition of done
- Mocked network fixtures yield every value HIST rules need. Rate limit, timeout, and 404 each resolve to `UNKNOWN` and never propagate as exceptions.

---

## 8. E05 — Sandbox runtime

### Runtime abstraction
```python
class Runtime(Protocol):
    def available(self) -> bool: ...
    def pull(self, image_ref: str) -> None: ...
    def run(self, spec: ContainerSpec) -> Container: ...  # start, exec, logs, stop, rm
```
- Implementations: `DockerRuntime`, `PodmanRuntime`. Auto-detect docker → podman; `--runtime` forces.
- If neither is installed: guidance with install link, exit 5.

### Images
- `ghcr.io/brnyxx/pano-sandbox-node:20`, `pano-sandbox-node:22`, `pano-sandbox-python:3.12`, `pano-sandbox-base` (glibc + strace + dnsmasq + ca-certificates), built for `linux/amd64` and `linux/arm64`. Digests are pinned in `sandbox/images.lock` and generated only from registry-resolved digests; `pano sandbox update` refreshes. Mutable tags may exist for readability, but the runtime resolves and trusts the digest (DECISIONS #1).
- Image selection by ecosystem: node/python; `docker:` wraps the user image on top of base; `local:` uses base.
- Package installation happens inside the container via `npx`/`uvx`. An install cache volume (`pano-cache`) speeds up repeat runs; it contains no user data.

### Isolation
- `--read-only` root, `tmpfs /tmp`, `tmpfs $HOME` (populated with decoys), `--cap-drop ALL --cap-add SYS_PTRACE`, `--security-opt no-new-privileges`, `--pids-limit 256`, `--memory 1g`, `--cpus 2`, uid 1000.
- Network: dedicated bridge `pano-net`. The sandbox can reach only the proxy container (`pano-proxy`) and DNS; all other egress is iptables DROP + LOG. Only the proxy egresses.
- Proxy: HTTP CONNECT + SOCKS5. Logs (ts, container, dst host, port, bytes; for plaintext HTTP: method, path, header sizes, body hash, decoy matches). TLS is never terminated.
- Never mount the user's home or project directory. No exceptions. Project files are name-only replicated by E06.

### Definition of done
- On both Docker and Podman, the evil fixture demonstrates: direct egress DROPPED, proxy egress OK, host files unreachable. Five known container-escape fixtures all fail.

---

## 9. E06 — Decoy system

### Decoy home

| Path | Content | Detects |
|---|---|---|
| `~/.ssh/id_ed25519`, `id_rsa`, `config`, `known_hosts` | well-formed fake keys | read |
| `~/.aws/credentials`, `config` | `AKIA` + decoy | read, leak |
| `~/.gitconfig` | fake name/email | read (review) |
| `~/.npmrc`, `~/.pypirc`, `~/.netrc`, `~/.docker/config.json` | fake tokens | leak |
| `~/.config/gcloud/`, `~/.azure/`, `~/.kube/config` | fake credentials | leak |
| `~/.bash_history`, `~/.zsh_history` | decoy sentences | read |
| `~/Documents/`, `~/Desktop/`, `~/Downloads/` | 5 files each with decoy sentences | broad read |
| `~/project/` | directory tree and filenames of `--project`, empty contents; `.env`-like files filled with decoys | path patterns |
| Browser profile stubs (e.g. Chrome `Default/Cookies`) | empty SQLite | read |

### Decoy environment variables
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `SLACK_TOKEN`, `NOTION_TOKEN`, `DATABASE_URL`, `STRIPE_SECRET_KEY`, `NPM_TOKEN`, … (30 total). Values follow real formats but embed `PANO_DECOY_<8 random chars>`, regenerated each run so hard-coded detection is hard.

### Real env passthrough
- Default: none. Keys from config `env_keys` are set to decoy values.
- `--real-env KEY[,KEY]`: only listed keys get real values; those values are registered for leak detection and never persisted.
- `--real-env-all`: warns, passes everything, forces destructive-tool protection (E08).

### Registry
- `DecoyRegistry`: (key, value, kind: file|env|content) with `match(bytes) -> list[DecoyHit]` using Aho-Corasick over proxy bodies, file writes, process args; also matches base64 and URL-encoded variants.

### Definition of done
- Decoy home builds in ≤1 s. 100% match on leak fixtures (plaintext HTTP, file write, exec arg, base64). Verified that the real home path string does not exist anywhere inside the container.

---

## 10. E07 — Event collection

### Sources and events

| Source | Events | Notes |
|---|---|---|
| `strace -f -ttt -yy -e trace=openat,open,stat,newfstatat,readlink,execve,execveat,connect,sendto,sendmsg,bind,clone,fork` | FileEvent(op read/write/stat/exec, path, decoy), ProcEvent(argv, parent), NetEvent(raw connect ip:port) | PID tree tracking |
| DNS log | NetEvent(dns, host, answer) | dnsmasq `log-queries` |
| Proxy log | NetEvent(connect, host, port, via=proxy, bytes), PlaintextHttp(method, path, decoy_hits) | |
| iptables LOG | NetEvent(blocked, ip:port) | bypass attempts |
| Home snapshot diff | FileEvent(write/create/delete) + decoy_hits | after container exit |
| stdout/stderr capture | decoy matching | servers that leak via stderr |

### Span attribution
- `probe` sends `SpanBegin(tool, ts)` right before the JSON-RPC request and `SpanEnd(ts)` on response. Container/host clock skew corrected at start by exchanging `date +%s.%N`.
- Reserved spans: `__install__`, `__startup__` (before initialize), `__idle__` (after last call, default 10 s, `--idle`), `__shutdown__`.
- Child-process events attribute to the parent's current span.

### Noise filter
- `sandbox/noise.yaml`: interpreter paths, `/proc`, `/sys`, `/dev`, `/etc/resolv.conf`, `/etc/hosts`, `/etc/ssl`, locale, tzdata, cache volume. Filtered counts are shown in the summary; `--raw` shows everything.
- Repeated (op, path) collapse into `count`.

### Definition of done
- 100% parse accuracy on 10 stored strace/netlog fixtures. Evil fixture events attribute to the correct tool span. Clock correction error ≤ 50 ms.

---

## 11. E08 — Probe

### MCP client (dual era)
- JSON-RPC 2.0 over stdio with bounded framing, request IDs, pagination primitives, cancellation, and frame and response size limits.
- **Modern era (`2026-07-28`)**: per-request metadata, server discovery, and version retry. Modern version discovery is its own stage; the legacy-only handshake is `NOT_REQUESTED`.
- **Legacy era**: `initialize` with the newest supported protocolVersion, one retry with an older revision, `notifications/initialized`, session behavior. Entered only through a typed fallback with a recorded reason.
- Transport era is cached per transport. `tools/list` (paginated), `resources/list`, `prompts/list`, and `tools/call` run only when the server advertises the matching capability.
- Record server capabilities, requested protocolVersion, selected protocolVersion, era, fallback reason, and serverInfo.
- Protocol and transport errors are typed. A stream that desynchronized after a timeout is not resumed.
- Timeouts: initialize 30 s, tools/list 20 s, tools/call 20 s (`--timeout`), total 300 s. On timeout mark the stage `INCOMPLETE` and continue.

### Argument generation (deterministic, seed = server_id)

| schema | value |
|---|---|
| string | `"panopticon-probe"`; `format:uri` → `https://example.com/pano`; `format:email` → `probe@example.com`; `format:date` → `2026-01-01`; name contains `path/file/dir` → `~/project/README.md`; `url` → uri above; `query/search/q` → `"panopticon"` |
| number/integer | `minimum` or 1; first enum value if enum |
| boolean | false |
| array | one item (recursive) |
| object | required only (recursive); ignore additionalProperties |
| oneOf/anyOf | first branch |
| missing/unknown | `{}` |

- `--calls N`: N invocations; from the 2nd, strings get `-2`, `-3` suffixes to defeat caching.
- `--args <tool>=<json>`: manual override per tool.

### Destructive-tool protection
- Name matches `delete|remove|destroy|drop|purge|force|cancel|pay|charge|send|post|publish|deploy|execute|run_command|shell` or description contains `irreversible|permanent|cannot be undone`.
- Decoy environment (no real env): call it.
- `--real-env` active: the call is not made by default — its outcome is `status=SKIPPED` with `reason_code=SKIPPED_DESTRUCTIVE`, and the aggregate probe stage is `PARTIAL`. `--allow-destructive` to call.

### `--self`
- Mount cwd MCP source read-only (the only permitted mount), build and run inside the container. Entry point inferred from `package.json` `bin` or `pyproject` scripts; `--command` overrides.

### Definition of done
- On 5 official example MCPs (filesystem, github, fetch, memory, sqlite) plus evil/clean fixtures: every tool call completes and generated args validate against the schema. Protocol-version mismatch, server crash, and no-response each map to distinct state codes.

---

## 12. E09 — Remote MCP observation (HTTP/SSE)

### Scope
- `transport: http` (Streamable HTTP) and `sse`. The remote server itself cannot be observed; record **what is visible from the client side**.
- Calls go through the local proxy: request URL, redirect chain, external resource references in responses, token kinds in headers (names only), response sizes.
- Leak detection: whether decoy values appear in request bodies/headers (config `headers` are swapped for decoys).
- Auth-requiring servers: `--real-header KEY` passes real headers.

### Rule mapping
- Redirect to a host outside the declared URL host → WATCH-003.
- Plaintext `http://` → CFG-008.
- Response with a large number of external URLs (prompt-injection vector) → WATCH-012 (info).

### Definition of done
- Four local test servers (normal / redirect / plaintext / decoy-reflecting) yield expected events. Remote observations always report `state.stages.file = UNSUPPORTED`.

---

## 13. E10 — Declared-scope extraction

### Sources and extractors

| Source | Extractor | Output |
|---|---|---|
| tool description / annotations (`readOnlyHint`, `destructiveHint`, `openWorldHint`) | `ToolDescExtractor` | hosts, paths, capabilities (read/write/destructive/open_world) |
| README (package tarball or GitHub) | `ReadmeExtractor` | hosts (domain regex, code blocks first), paths (`~/`, `/`), env (UPPER_SNAKE in code blocks / `export` / `=` context), permission sentences ("requires access to …") |
| `package.json` / `pyproject.toml` | `ManifestExtractor` | homepage, repository host, bin |
| config `env_keys`, `args` | `ConfigExtractor` | user-granted env, path args |
| MCP Registry `server.json` | `RegistryExtractor` | remotes, environment_variables, packages |
| `.panopticon.yaml` (maintainer self-declaration in repo) | `SelfDeclExtractor` | hosts, paths, env, processes — highest priority |

### `Declared` object
- hosts (normalized, wildcards allowed), paths (globs), env, processes (allowed binaries), capabilities, sources[], completeness: `COMPLETE` (self-decl or registry present) / `PARTIAL` (README/description only) / `NONE`.
- `NONE` demotes every observation to `review`. `PARTIAL` allows `confirmed` but the report shows "declared source: inferred from README".

### `.panopticon.yaml` spec (for maintainers)
```yaml
version: 1
hosts: [api.github.com, "*.githubusercontent.com"]
paths: ["~/.gitconfig"]
env: [GITHUB_TOKEN]
processes: [git]
notes: "gitconfig is read only to display the user name"
```
- This file is a prerequisite for the badge (E17).

### Definition of done
- ≥90% host/env extraction accuracy on the 5 official example MCP READMEs (vs. manual labels). Self-declaration parsing and priority-merge tests.

---

## 14. E11 — Finding model and rule engine

### Finding (upstream-extended)
- Kept: `id`, `rule_id`, `severity` (HIGH/MEDIUM/LOW/INFO), `title`, `evidence[]`, `location`.
- Added: `kind` (confirmed/review/info), `server_id`, `observation_id`, `span_ref`, `remediation_key`, `fix_available`, `declared_source`, `first_seen`, `suppressed_by`.
- Two identities per finding:
  - `logical_key = rule_id | installation_id | subject` — stable across runs and independent of evidence, so diff classifies an evidence change as `CHANGED` rather than `RESOLVED` plus `NEW`.
  - occurrence id = `sha256(rule_id | installation_id | normalized_evidence)[:16]` — addresses one concrete instance.
- Evidence normalization: paths → `~`, hosts lowercase, drop ports 443/80, sort.

### Rule engine
```python
@rule(id="WATCH-001", severity="HIGH", kind="confirmed", line="observe")
def decoy_leak(ctx: RuleContext) -> Iterable[Finding]: ...
```
- `rules/registry.py` collects via decorator. Metadata: id, severity, kind, line, fix_id, i18n key, since_version.
- `RuleContext`: inventory, observation, declared, history, config, allowlist, previous_baseline — each optional source carries an explicit state so a rule can tell "absent" from "not collected".
- Rules run isolated. A rule failure produces a sanitized diagnostic, not an invented finding, and never escapes the boundary. One failing rule never blocks the report.
- Rules read no clock, no network, and no filesystem directly; every input arrives through `RuleContext`.
- Suppression: `~/.panopticon/suppress.yaml` entries `rule_id + server_id + reason + expires`. Suppressed findings are kept with `suppressed_by` and counted in the summary.

### Definition of done
- Rule metadata schema validation. CI enforces that every registered rule has ≥1 fixture test. Canonical-id stability test (order/timestamp changes keep the id).

---

## 15. E12 — Rule implementation

Implement all of §20: CFG-001..012, HIST-001..004, WATCH-001..014. Each rule has a condition function, evidence construction, fix_id link, i18n key, ≥1 positive and ≥1 negative fixture. Allowlist-referencing rules record "excluded items" in evidence.

### Initial allowlist
- Install span only: `registry.npmjs.org`, `registry.yarnpkg.com`, `pypi.org`, `files.pythonhosted.org`, `github.com`, `objects.githubusercontent.com`, `*.cloudfront.net`
- Always: none. Users may add via `config.toml` `allow.hosts`; additions are labeled "user-allowed" in reports.

### Definition of done
- All 30 rules green on fixtures. Evil fixtures (5) produce exactly the expected finding sets; clean fixtures (5) produce zero `confirmed`.

---

## 16. E13 — Fix

### Flow
`pano fix [<server>] [--rule ID] [--yes] [--dry-run]`
1. Collect findings with `fix_available`.
2. Each FIX rule builds `plan() -> FixPlan(edits[], prompts[])`; edits are JSON patches by path, prompts are user inputs (e.g., directory choice).
3. Print a unified diff per file. Without `--yes`: Enter / n / q.
4. Backup: `<config>.pano-bak-<ts>` (0600); record in `~/.panopticon/fix-journal.ndjson`.
5. Apply while preserving indentation, key order, and comments (JSONC round-trip parser).
6. Re-check: re-run the rule; if not `RESOLVED`, auto-rollback and error.
7. `pano fix --undo [<journal-id>]` restores.

### FIX rules (§20.4)
- FIX-001: move the token into the OS credential store through `SecretStore` and leave a `${KEY}` reference in the config. If the client lacks env-reference support (Claude Desktop), fall back to wrap-injected env sourced from `SecretStore` and suggest `install`. If no secure backend is available, or both paths are declined, the fix is **guidance only** and nothing secret-bearing is written. Panopticon never writes a plaintext env file (DECISIONS #10).
- Backups of secret-bearing configs are encrypted with authenticated encryption whose key lives in the credential store. Plain configs are backed up as-is. Diffs and journal entries redact secret material.
- FIX-002: pin version.
- FIX-004: narrow filesystem path (prompt).
- FIX-005: unify duplicates (prompt).
- FIX-008: `http` → `https` for remote URLs only after a bounded `POST` returns a
  protocol-valid MCP `initialize` result. `HEAD` or generic HTTP success is insufficient.
- FIX-010: remove disabled entries (prompt).

### Definition of done
- On fixtures for all 6 clients: fix → re-check RESOLVED → undo → original hash matches. Comment/indent preservation test. Concurrent-edit detection (re-hash immediately before apply).

---

## 17. E14 — Baseline & diff

### Baseline
- `pano baseline create [--label]`: snapshot of current inventory + latest observation per server + findings to `~/.panopticon/baselines/<id>.json`.
- `pano baseline list|show|rm`.
- Implicit baseline: no explicit baseline → most recent observation → config mtime + registry history (used by HIST rules).

### Diff
- `pano diff [<server>] [--since <id|auto>] [--json]`
- Canonicalize: sort arrays, strip timestamps/PIDs/durations/container IDs, collapse repeats, normalize decoy keys. DNS and connect events are correlated, never blindly merged. Run metadata is compared separately from the semantic view.
- Findings are joined by `logical_key`, so evidence changes classify as `CHANGED`.
- Delta classes:
  - finding: `NEW / CHANGED(severity|evidence|scope) / UNCHANGED / RESOLVED / UNKNOWN (stage mismatch)`
  - capability: `NEW_TOOL / REMOVED_TOOL / SCHEMA_CHANGED / ANNOTATION_CHANGED`
  - behavior: `NEW_HOST / REMOVED_HOST / NEW_PATH / NEW_PROCESS / NEW_LEAK`
  - inventory: `ADDED / REMOVED / COMMAND_CHANGED / VERSION_CHANGED / ENV_KEYS_CHANGED`
- "Meaningful" (surfaced at the top): NEW_LEAK, NEW_HOST, NEW_TOOL (destructive), SCHEMA_CHANGED, COMMAND_CHANGED, major VERSION_CHANGED, NEW HIGH/MEDIUM finding. Everything else is collapsed.
- Coverage rule: absence is `RESOLVED` or `REMOVED` only when both sides have complete coverage for that category. Otherwise it is `UNKNOWN`.

### Definition of done
- Same semantic input twice → zero diff in every category. 12 fixture mutations (one per delta) → exact delta. Observations with different stage coverage report `UNKNOWN` for that category, in both directions. Duplicate installations diff independently by `installation_id`. Migration replay from every shipped 0.x version converges idempotently.

---

## 18. E15 — Wrap & install

### `pano wrap -- <command...>`
- Transparent stdio relay: spawn child, pass stdin/stdout bytes through, ≤1 ms latency (async I/O; parsing in a separate task).
- JSON-RPC framing (newline-delimited). Match `tools/call` request ids to responses to form spans. On parse failure stop recording but keep relaying.
- Observation: Linux with `strace` → file+network; otherwise `/proc/<pid>/net/tcp` polling for connect targets. macOS: `nettop`/`lsof` polling (1 s) for connect targets; file observation `UNSUPPORTED`.
- Env injection: resolve the values from `SecretStore` at launch and pass them to the child in memory (the FIX-001 fallback path). Panopticon never writes a plaintext env file, and injected values are registered for leak detection so they cannot reach a wrap record (DECISIONS #10).
- Records: immutable `~/.panopticon/wrap/<installation_id>/<date>/<span_id>.json`
  artifacts through `store/`, partitioned by UTC day with 30-day retention (`config.toml`).
  Immutable per-call files avoid cross-process append corruption and preserve installation identity
  (DECISIONS #17).
- Alerts: first-seen host/process appended to `~/.panopticon/alerts.ndjson`; `pano doctor` shows them at the top. `--notify` for OS notifications (macOS `osascript`, Linux `notify-send`).
- Self-protection: if wrap crashes the child must survive (detach option); crash log recorded.

### `pano install <client> [--only <server>]` / `pano uninstall`
- Replace `command` with `pano` and `args` with `["wrap","--",<original command>,<original args>...]` for all (or selected) stdio servers in the client. Original preserved under `_pano_original`.
- Dry-run diff → confirm → backup → apply → restart hint. Same journal/undo as E13.
- Skip already-wrapped entries. `uninstall` restores `_pano_original`.
- Remote MCPs are not install targets (guidance only).

### Definition of done
- 5 official example MCPs work through wrap in Claude Desktop/Claude Code (documented manual procedure + automated protocol test). Latency benchmark ≤ 1 ms. Install/uninstall round-trip hash match on 6 client fixtures.

---

## 19. E16 — Analyze line (upstream stabilization)

### Scope
- Vendor upstream modules into `analyzers/static`, `analyzers/semantic`, `analyzers/dependency` from pinned commit `e717e955`, preserving MIT headers, per-file provenance and checksums, and `THIRD_PARTY_NOTICES.md` entries. The dynamic probe is replaced by the E07/E08 engine. Import-path shims only where external compatibility is explicitly required.
- **Read-only upstream reference (DECISIONS #13a).** When upstream business logic is needed in context, clone `https://github.com/BashaarJavaid/MCP-Sentinel` into a disposable directory outside the repository and read it there. The clone is never modified, never vendored from, and never merged as Git ancestry: the only vendorable source is `e717e955`, resolved by hash. Enumerate the selected upstream test IDs explicitly. Delete the clone after task 21 and prove the path is absent.
- `pano scan <path> [--mode quick|standard|deep]`
  - quick: config (example configs in the target repo), Python AST (SENT-001..007), dependency lock parsing.
  - standard: + Semgrep, OSV/advisory lookup.
  - deep: + semantic reviewer, + dynamic probe (= `watch --self` engine). The semantic reviewer is the product's one explicit network exception (DECISIONS #12): it runs only when the user selects deep mode, uses the user's own API key, prints the exact payload disclosure before the first request, sends redacted excerpts only, and is disabled by `--offline`. Under `--offline` the semantic result is typed `UNSUPPORTED` and the scan result is `INCOMPLETE`; it is never reported as a pass. Cassette boundaries are deterministic; live model prose is never asserted as deterministic output.
- Restore upstream replay demo: resolve cassette fingerprint drift, reproduce `COMPLETE` in deep mode. Document re-recording if the cause is external API change.
- Dependency audit green or verified exceptions with expiry.
- TypeScript static analysis: v1.0 ships a Semgrep rule set (10 rules) only; AST analysis is post-1.0.
- `pano ci`: GitHub Action entry point. quick/standard, SARIF upload, exit policy (required stage INCOMPLETE = 3, HIGH confirmed = 1, review = 0), scheduled audit workflow template.

### Definition of done
- Upstream 125 tests + migrated tests green, with the selected upstream test IDs enumerated in the manifest. Every vendored file resolves to `e717e955` by checksum. Any disposable reference clone is deleted and its path proven absent. Replay demo `COMPLETE`. SARIF validates against GitHub Code Scanning schema. E2E workflow runs the Action from a clean checkout.

---

## 20. Complete rule catalog

### 20.1 CFG (config)

| ID | sev | kind | condition | fix |
|---|---|---|---|---|
| CFG-001 | HIGH | confirmed | env value matches a known token pattern (ghp_, github_pat_, sk-, sk-ant-, xox[abp]-, AKIA, AIza, glpat-, hf_, pypi-, npm_, JWT) | FIX-001 |
| CFG-002 | MEDIUM | confirmed | package version unpinned (`@latest` / no tag) | FIX-002 |
| CFG-003 | MEDIUM | review | command contains `sh -c`, `bash -c`, `curl\|sh`, `powershell`, `eval` | — |
| CFG-004 | HIGH | confirmed | filesystem-class MCP allowed path is `~`, `/`, `$HOME`, or a drive root | FIX-004 |
| CFG-005 | LOW | info | same server_id installed multiple times with version mismatch | FIX-005 |
| CFG-006 | MEDIUM | review | package source unverifiable (not in registry, local) | — |
| CFG-007 | LOW | review | env contains ≥20-char high-entropy string (unknown pattern) | FIX-001 |
| CFG-008 | MEDIUM | confirmed | remote URL is plaintext http | FIX-008 |
| CFG-009 | INFO | info | disabled server | FIX-010 |
| CFG-010 | MEDIUM | review | args contain absolute system paths outside home (`/etc`, `/var`, `/usr`) | — |
| CFG-011 | LOW | review | remote MCP headers contain a token pattern | FIX-001 |
| CFG-012 | INFO | info | stdio server not wrapped | suggest install |

### 20.2 HIST (history)

| ID | sev | kind | condition |
|---|---|---|---|
| HIST-001 | INFO | info | ≥1 release since baseline (or config mtime) |
| HIST-002 | MEDIUM | info | major version jump since baseline |
| HIST-003 | HIGH | review | npm maintainers changed since baseline |
| HIST-004 | MEDIUM | info | repository archived or 12 months without activity |

### 20.3 WATCH (behavior)

| ID | sev | kind | condition |
|---|---|---|---|
| WATCH-001 | HIGH | confirmed | decoy value exfiltrated via network, file, process arg, or stderr |
| WATCH-002 | HIGH | confirmed | credential decoy file read without declaration |
| WATCH-003 | MEDIUM | confirmed | connection to undeclared host (allowlist excluded) |
| WATCH-004 | MEDIUM | confirmed | network activity in `__idle__` span |
| WATCH-005 | MEDIUM | confirmed | non-registry host during `__install__` |
| WATCH-006 | LOW | review | personal config file (`.gitconfig`, shell rc) read without declaration |
| WATCH-007 | MEDIUM | confirmed | proxy bypass attempt (DROP) |
| WATCH-008 | MEDIUM | confirmed | undeclared external process (interpreters, git, npm, uv excluded) |
| WATCH-009 | LOW | info | broad enumeration (≥10 stat/read under `Documents/Desktop/Downloads`) |
| WATCH-010 | INFO | info | declared = observed (badge condition; requires declared COMPLETE) |
| WATCH-011 | — | review | verdict withheld because declared is NONE/PARTIAL |
| WATCH-012 | INFO | info | remote response contains many external URLs |
| WATCH-013 | MEDIUM | confirmed | tool declared `readOnlyHint: true` performs a write or network POST |
| WATCH-014 | MEDIUM | confirmed | network activity in `__startup__` span (pre-handshake beacon) |

### 20.4 FIX

| ID | targets | action |
|---|---|---|
| FIX-001 | CFG-001/007/011 | move token to env file; `${KEY}` reference or wrap injection |
| FIX-002 | CFG-002 | pin resolved version |
| FIX-004 | CFG-004 | narrow path (prompt) |
| FIX-005 | CFG-005 | unify versions (prompt) |
| FIX-008 | CFG-008 | switch to https (after check) |
| FIX-010 | CFG-009 | remove disabled entries (prompt) |

### 20.5 SENT (upstream)
SENT-001..011 preserved. Details migrated to `docs/rules/sent.md`.

### 20.6 Required rule inventory

| Family | Count | IDs |
|---|---|---|
| CFG | 12 | CFG-001..012 |
| HIST | 4 | HIST-001..004 |
| WATCH | 14 | WATCH-001..014 |
| **Observe subtotal** | **30** | CFG + HIST + WATCH |
| FIX | 6 | FIX-001, 002, 004, 005, 008, 010 |
| SENT | 11 | SENT-001..011 |
| **Total documented rules** | **47** | 30 + 6 + 11 |

The i18n manifest requires ko and en documents for all 47 IDs (§27). The rule checker fails on any missing ID, missing document, or missing positive or negative fixture. Changing a count requires amending this table and `docs/DECISIONS.md` in the same change.

---

## 21. Data schemas (summary)

JSON Schema in `schemas/`, generated and validated from the runtime models. The development line
used `schema_version: "0.1"`; `1.0` was frozen exactly once at the 0.9 release-candidate gate with
idempotent migration replay (§23, DECISIONS #6).

### InstalledServer
`schema_version, server_id, installation_id, name, client, config_path, config_pointer, scope, transport, command, args[], env_keys[], url, headers_keys[], package{ecosystem,name,pinned,resolved}, source{kind,url}, identity_confidence, disabled, wrapped`

### Observation
`schema_version, observation_id, server_id, installation_id, observed_at, pano_version, sandbox{runtime,image,image_digest,tracer}, package_resolved, protocol{era,requested_version,selected_version,discovery_reason,fallback_reason,server_info,capabilities}, tools[{name,input_schema_hash,annotations}], spans[{span_id,tool,call_index,args_fingerprint,result,duration_ms,events[]}], declared{hosts,paths,env,processes,capabilities,sources,completeness}, findings[], state{overall,stages{install,startup,version_discovery,handshake,probe,idle,declared,file,net},coverage{file,net,process,dns,proxy,snapshot,stdio}}`

Every stage and coverage entry is `{status, reason_code}` with status drawn from `COMPLETE | PARTIAL | INCOMPLETE | FAILED | UNSUPPORTED | SKIPPED | NOT_REQUESTED`. For a modern-era run, `handshake` is `NOT_REQUESTED`. Those seven values are the whole status enum: a domain outcome such as a destructive-tool skip is carried as a `reason_code` on the applicable status (`SKIPPED_DESTRUCTIVE` on `status=SKIPPED`), never as an eighth status, so no per-domain vocabulary may widen this enum.

### Event
`kind(file|net|proc|leak|blocked|plaintext_http), op, path|host|argv, port, via, decoy, decoy_key, sink, count`

### Finding
Per E11, including both `logical_key` and the occurrence id.

### Baseline
`schema_version, baseline_id, created_at, label, kind(explicit|last_observation|implicit_mtime), inventory[], observations[], findings[]` — self-contained and immutable; a baseline never references mutable external state.

### DiffResult
`schema_version, since, until, findings{new,changed,unchanged,resolved,unknown}, capability[], behavior[], inventory[], meaningful[]`

### WrapRecord (NDJSON)
`schema_version, ts, server_id, installation_id, span{span_id,tool,request_id,duration_ms}, events[], coverage`

### Common constraints
- No schema may contain a real home absolute path, a raw token, a `--real-env` value, or plaintext Panopticon-managed secret material. `util/leak_check` enforces this immediately before persistence, from inside `store/`, which is the only writer.
- Paths `~`-relative, hosts lowercase, times UTC ISO-8601.
- No incomplete nested record: a nested object is either fully populated or explicitly absent with a reason.

---

## 22. Quality, security, and documentation standards

### Tests
- Unit tests for every module. Rules require positive/negative fixtures (CI-enforced).
- Integration: 5 evil fixture MCPs (each specialized: file read, host connect, leak, idle beacon, process exec), 5 clean, 5 official examples. Docker-requiring tests run in a separate job.
- E2E: `pano doctor`, `pano watch`, `pano fix`, `pano wrap` scenarios in a clean container.
- Determinism: repeat-run zero-diff tests for observations, baselines, and every reporter.
- Leak: 20+ fixtures (token patterns, native and WSL home paths, real-env values, escaped, URL-encoded, form-encoded, base64, and chunk-split variants; covering logs, PNG, SVG, SARIF) — every persist sink must reject.
- Performance job: doctor 5 s, single watch 60 s (warm cache), decoy home 1 s, wrap 1 ms added latency on a fixed workload, diff 5 s. Each target names its runner hardware class, OS, runtime and image digests, fixture version, warm or cold cache state, sample count, and percentile method. Cold image-pull targets are measured separately.
- No fixed sleeps and no polling loops. Async tests subscribe to the exact signal and await it with a bounded timeout.
- Coverage ≥ 85%, and `fail_under` may only rise.

### Security
- Container isolation regression tests (§8) on rootful Docker, rootful Podman, and rootless Podman, with honest `PARTIAL` states where runtime guarantees differ.
- Dependency lock, scheduled OSV scan, exceptions with expiry.
- `SECURITY.md` names GitHub Private Vulnerability Reporting on `brnyxx/panopticon` as the only official intake (DECISIONS #14). No security email address is published.
- Release binaries signed (Sigstore), SBOM and provenance attached, images signed and trusted by digest.
- Run `pano scan --mode standard` on this repository in CI.

### Documentation (`docs/`)
- README ko/en (30-second demo, one-line install, three principles, the current repository and image namespaces)
- `architecture.md`, `rules/` catalog (generated), `limitations.md` (all limits from §8 and §12), `privacy.md` (exhaustive list of network use), `sandbox.md`, `self-declaration.md` (`.panopticon.yaml`), `disclosure.md`, `contributing.md` (how to add adapters/rules), `THIRD_PARTY_NOTICES.md`
- Every rule: `i18n/{ko,en}/rules/<ID>.md` with 6 sections (Problem / Impact / Evidence / Recommended action / How to verify / Limits). Forbidden-phrase lint.

### Disclosure policy
- Governs the project (not the tool) when publishing observations of popular MCPs. `docs/disclosure.md`.
- Contact: GitHub Private Vulnerability Reporting on the affected server's repository, the same intake `SECURITY.md` publishes for Panopticon (DECISIONS #14). It is the sole official channel; no maintainer email address and no private issue request is offered or published. Where the observed project has no such form, the observation waits until its maintainers open one. Embargo: leak (WATCH-001) 30 days, others 14 days. No response → publish facts only. Publication format: observation JSON + reproduction command. Never published: exploitation method, decoy generation details.

---

## 23. Version stages

Versions advance by **closed epics**, not by dates.

`0.1` through `0.9` are internal development and schema milestones: capability checkpoints that mark which epics are closed and which shapes the persisted schema has reached. They are not promises to publish, and none of them is released to a public channel. The first public release in this accepted execution is `1.0.0`, after every release gate in §22 and E19 has passed.

| Version | Epics to close | What the user can do |
|---|---|---|
| 0.1 | E01, E02, E03, E04, E11, E12 (CFG/HIST), E17 (terminal/json) | `pano doctor` — discovery, config checks, history |
| 0.2 | E05, E06, E07, E08, E10, E12 (WATCH), E18 (ko) | `pano watch` — stdio observation, declared comparison |
| 0.3 | E13, E14 | `pano fix`, `pano diff`, baselines |
| 0.4 | E15 | `pano wrap`, `pano install` |
| 0.5 | E09, E17 (PNG/badge/Markdown) | remote MCPs, share card, badge |
| 0.6 | E16 | `pano scan`, GitHub Action, upstream replay restored |
| 0.7 | E18 (en), all 6 clients, WSL2 | multilingual, all clients |
| 0.8 | E19 (distribution: binaries, brew, signing, SBOM) | every install path |
| 0.9 | all quality standards (§22), schema 1.0 frozen, all docs | release candidate |
| **1.0.0** | entire §2 checklist | — |

Persisted schemas developed on the `0.x` line. The migration to `1.0` happened exactly once at the
0.9 gate and froze the ID formats, stage reason codes, event, finding, baseline, diff, and wrap
shapes, the canonicalizer version, the CLI exit codes, and the `_pano_original` v1 representation.
Post-1.0 breaking schema changes are 2.0 and need their own release plan.

---

## 24. Open decisions

All pre-epic decisions are now closed in `docs/DECISIONS.md`:

| Question | Entry | Resolution |
|---|---|---|
| Container image registry org | #1 | `ghcr.io/brnyxx` |
| Final initial allowlist (§15) | #2 | `analyzers/behavior/allow.yaml`, install span only |
| `wrap` OS notification default | #3 | off; `--notify` opts in |
| Host wildcard syntax in `.panopticon.yaml` | #4 | leading `*.` only |
| PNG card design | #5 | deterministic terminal-style evidence card |
| Schema lifecycle | #6 | 0.x development, one 1.0 freeze at the 0.9 gate |
| Installation versus server identity | #7 | `installation_id` beside `server_id` |
| Stage result structure | #8 | status + `reason_code` + coverage |
| Persistence boundary | #9 | one gateway in `store/` |
| Secret storage | #10 | OS credential store, encrypted backups, guidance-only fallback |
| MCP protocol eras | #11 | modern `2026-07-28` plus legacy fallback |
| Semantic-analysis network use | #12 | user-invoked, user-keyed, disclosed, redacted, `--offline` disables |
| Upstream provenance | #13 | pinned `e717e955` with per-file checksums |
| Upstream reference clone | #13a | disposable read-only clone, deleted after task 21 |
| Vulnerability intake | #14 | GitHub Private Vulnerability Reporting |
| Forbidden verdict terms | #15 | `glossary.yaml` phrases plus ground rule 1 terms |
| History normalization | #16 | archive tag, then one leased force push |

Decide after start:
- eBPF tracer migration (once privilege issues are solved)
- macOS wrap file observation (EndpointSecurity requires signing; deferred)
- TypeScript AST static analysis
- Whether to publish exported observations as a public dataset
- Organization features (private inventory, policies, alert channels)

---

## 25. Product description (final)

> Panopticon is a watchtower for MCPs. It watches your MCPs, not you. `pano doctor` finds the MCP servers installed across six AI clients, shows config risks and what changed since you last looked, and fixes them with a single Enter. `pano watch` runs an MCP inside a decoy-filled isolated environment, calls its tools for real, records every file, network, process, and leak event per tool, and compares that against what the server declared. `pano wrap` makes that continuous, `pano diff` compares then and now, and `pano scan` keeps static, semantic, and dynamic analysis in the MCP author's CI. What was not observed is never called safe. Every finding is explained, in Korean and English, with problem, impact, evidence, action, verification, and limits.

---

## 26. E17 — Reporters, evidence card, and badge

### Scope
- One immutable **sanitized render model** built from the observation, findings, declared scope, and coverage. Reporters read only this model; they never touch raw evidence, secrets, or the store's inputs.
- Five reporters plus one badge: terminal (rich), JSON, SARIF 2.1.0, Markdown, PNG evidence card, SVG badge.
- Terminal: stable table order, plain mode, explicit TTY versus non-TTY color rules, ko/en text, machine fields left unlocalized, results on stdout and diagnostics on stderr.
- JSON: canonical field order, visible per-stage coverage, allowlist-excluded evidence retained, suppressed counts shown.
- SARIF: GitHub-compatible, stable rule metadata, relative normalized URIs, partial fingerprints derived from `logical_key`, unique automation category per line, escaping against Markdown and URI injection.
- Markdown: deterministic section order, injection-safe escaping of every server-supplied string.
- PNG evidence card: deterministic high-contrast terminal-style card (DECISIONS #5) with bundled fonts, fixed layout, color tokens, and compression, stripped metadata, ko/en text, CJK-safe overflow handling, and visible observation date and coverage.
- SVG badge: accessible, with a text alternative, carrying the observation date.

### Interfaces
```python
class Reporter(Protocol):
    name: str

    def render(self, view: RenderView) -> RenderedArtifact: ...


class RenderView(Protocol):  # immutable, pre-sanitized
    installations: Sequence[InstallationView]
    findings: Sequence[FindingView]
    coverage: CoverageView
    suppressed: SuppressionSummary
    locale: Locale
```
- Every artifact is written through `store/`; no reporter opens a file itself.
- Badge eligibility is a single predicate: declared completeness is `COMPLETE`, every applicable stage is `COMPLETE`, no uncovered events, no leak findings, and no suppression hiding a declared-versus-observed mismatch. Any other state denies the badge.

### Tests
- Fixed fixtures render byte-stable terminal, plain, JSON, Markdown, SARIF, PNG, and SVG output across repeat runs.
- TTY and non-TTY, ko and en, suppressed, `PARTIAL`, `UNKNOWN`, `UNSUPPORTED`, empty, and failure states each render explicitly.
- Secret-bearing evidence is rejected before emission and leaves no partial file behind.
- SARIF validates against the GitHub Code Scanning schema and stays within its size limits; a policy finding still produces a complete artifact before the non-zero exit.
- Hostile Markdown and absolute-home URIs are escaped or rejected.
- Visual QA covers dimensions, contrast, CJK clipping, long strings, and empty PNG metadata.
- Badge denial cases: partial declaration, partial stages, active suppression, any leak.

### Definition of done
- All six output forms render deterministically from fixed fixtures with stable hashes, pass leak and phrase checks, and are written only through `store/`. SARIF uploads successfully from CI. The badge predicate rejects every denial case above, and no output contains a forbidden verdict term.

---

## 27. E18 — i18n, rule documentation, and `pano explain`

### Scope
- Bilingual documentation for the full rule inventory in §20.6: 30 observe rules (12 CFG + 4 HIST + 14 WATCH), 6 FIX rules, and 11 SENT rules.
- Every rule ships `i18n/en/rules/<ID>.md` and `i18n/ko/rules/<ID>.md` with the identical six sections from `i18n/RULE_TEMPLATE.md`: Problem, Impact, Evidence, Recommended action, How to verify, Limits.
- Message catalog with locale precedence (CLI flag > `PANO_LANG` > OS locale > `en`) and explicit fallback to `en` when a key is missing in `ko`.
- Generated rule catalog under `docs/rules/`, regenerated by `scripts/gen_rule_catalog.py` and idempotent.
- `pano explain <RULE-ID>` renders the six sections in the active locale.
- CJK-safe rendering and UTF-8 handling on Windows terminals.
- Glossary and forbidden-phrase lint across every user-facing surface, including generated catalogs.

### Interfaces
```python
def explain(rule_id: RuleId, locale: Locale) -> RuleDoc          # six sections, always
def t(key: MessageKey, locale: Locale, **params: object) -> str  # falls back to en
```
- Machine-consumed values (rule IDs, severities, kinds, reason codes, stage names) are never localized.

### Tests
- ID parity: the `ko` and `en` document sets are identical and match the expected manifest exactly; a missing document fails the manifest check.
- Section-structure check: all six sections present, in order, in both languages.
- Locale precedence and fallback, including a key present in `en` and missing in `ko`.
- Generated catalog is clean and idempotent across repeated generation.
- `pano explain` handles a known ID, an unknown ID, and a locale fallback.
- Forbidden-phrase lint passes over source, docs, and generated output.
- Prose wording is never asserted. Tests cover IDs, structure, lookup, fallback, and equality of generated copy.

### Definition of done
- Every ID in §20.6 has both language documents with all six sections, the expected-document manifest passes with zero missing or extra entries, the generated catalog is idempotent, `pano explain` works in both languages including fallback, and the phrase lint is clean.

---

## 28. E19 — Distribution, security verification, and release

### Scope
- **Platform and runtime verification.** Distinct CI gates for macOS arm64 and x86_64, Linux amd64 and arm64, native Windows discovery, and WSL2 sandboxing. WSL2 runs on the self-hosted runner labelled `self-hosted,Windows,X64,wsl2,panopticon`. Container isolation is verified on rootful Docker, rootful Podman, and rootless Podman, with honest `PARTIAL` states where runtime guarantees differ. No live kernel exploits; no unsupported dimension is reported as complete.
- **Release prerequisites, provisioned before any tag.** Least-privilege GitHub environments and branch rules, GitHub Private Vulnerability Reporting as the official intake (DECISIONS #14), PyPI and TestPyPI trusted publishers, GHCR package permissions under `ghcr.io/brnyxx`, the `brnyxx/homebrew-tap` repository, required architecture runners, and third-party actions pinned by commit SHA. Fail closed: no partial publication, no invented credential or contact data.
- **Schema and patch-release version contract.** Migrate every persisted `0.x` shape to schema `1.0` exactly once on `release/v1.0.0` (§21, §23). Schema `1.0` remains frozen for patch releases. `[project].version` in `pyproject.toml` is the sole patch-release version authority; a checked-in resolver validates stable `X.Y.Z` input and supplies controlled workflow outputs. The immutable `1.0.0` publication remains rollback and history evidence.
- **Build once, promote the same bytes.** Wheel and sdist via `uv build --no-sources`; reproducible single-file binaries for Linux x86_64 and arm64 and macOS x86_64 and arm64 with bundled licenses, fonts, schemas, and rules. Produce a SHA-256 manifest, SBOM, provenance, and Sigstore bundles. Publish jobs never rebuild, overwrite, or substitute artifacts.
- **Images.** Multi-architecture `linux/amd64` and `linux/arm64` builds of base, node20, node22, and python3.12, scanned, signed, pushed by digest, and recorded in `sandbox/images.lock` from registry-resolved digests only. Public visibility comes last, after PyPI and the GitHub Release.
- **Promotion order and recovery.** Quality and platform gates → artifacts → clean-install, signature, and SBOM verification → TestPyPI publish and install → GitHub draft asset verification → GHCR digest verification → Homebrew formula audit, install, and test. Publication to the first public channel begins only after every prerequisite in this list has passed, so the fail-closed rule above is never in tension with recovery. The rehearsal handoff records its workflow run ID and source SHA with the retained asset bundle and manifest. Before production promotion or recovery, re-verify that retained bundle byte-for-byte against the rehearsal manifest, signatures, SBOM, provenance, and hashes. Recovery applies only to an unavoidable failure that occurs after a public channel has already succeeded: it is append-only and resumes the remaining channels alone, promoting the byte-identical immutable artifacts and hashes produced by the single build, never rebuilding and never overwriting what was published. Patch releases reuse locked GHCR digests rather than rebuilding images. A published version is never reused or overwritten.
- **History normalization.** One archive tag `archive/pre-normalization-main-20260826` at the old remote root, then a single leased force push (DECISIONS #16). Archive tags follow `archive/<reason>-<YYYYMMDD>`. No later force push is authorized.
- **Documentation.** README ko/en, architecture, generated rule catalog, limitations, privacy data-flow inventory, sandbox model, self-declaration, disclosure, contributing, release/install/upgrade/migration/rollback, per-channel install docs, the supported-target matrix, retention and cleanup, the semantic-analyzer exception, and the vulnerability intake. No local-only claim while registry, semantic, or MCP traffic occurs; no certification or compliance claim.

### Interfaces
- `scripts/run_platform_matrix.py` — requires every named platform dimension and emits a signed evidence manifest.
- `scripts/release_preflight.py` — proves each destination exists and is writable, and is drift-free across two runs.
- `scripts/verify_release_assets.py` — verifies downloaded artifacts, signatures, SBOMs, and clean installs.
- `scripts/verify_images.py` — resolves manifests to signed digests and runs the isolation smoke suite against them.
- `scripts/verify_public_release.py` — queries every public channel after publication.

### Tests
- Every platform and runtime job produces an evidence manifest binding commands, platform, commit, and digests.
- Isolation inspections prove no prohibited mount or privilege, exact pinned options and digests, blocked direct egress, forced DNS, cache isolation, and zero orphan resources.
- A weakened runtime inspection, a stale or tampered artifact, a missing permission, an offline WSL2 runner, or a digest and tag mismatch each blocks the release.
- Migration corpora from every shipped 0.x version converge idempotently to `1.0`; unknown-newer and malformed inputs are left unmodified.
- A simulated Homebrew failure after PyPI resumes the remaining channels with the same artifacts and does not reuse the version; production and recovery reject a missing rehearsal run ID or source SHA, or any retained byte that differs from the rehearsal manifest.
- Docs contract: no stale command, no placeholder, no forbidden verdict term, and a clean-user walkthrough that runs against the release candidate.

### Definition of done
- Every platform and runtime gate is green with its evidence manifest; native Windows and WSL2 are separately proven. Schema `1.0` remains frozen, and the release version is resolved solely from `[project].version` in `pyproject.toml` as a stable `X.Y.Z` value. The public GitHub Release carries four binaries, wheel, sdist, checksums, SBOMs, and signatures; PyPI hashes match the tested artifacts; GHCR digests match `sandbox/images.lock` and pull anonymously; the Homebrew formula audits, installs, and reports the resolved version. The recorded rehearsal workflow run ID and source SHA bind the retained bundle, whose bytes have been re-verified exactly before production promotion or recovery. `uvx`, `pipx`, and direct binary installs all work on a clean host. CI and the repository self-scan are green on the tag. Every epic row in `docs/PROGRESS.md` is CLOSED with an evidence link, and no `OWNER`, `<domain>`, TODO release step, or mutable third-party action remains.

---

## 29. E20 — npm native distribution and production hardening

### Scope
- **Frozen npm identity and platform boundary.** Publish exactly `@brnyxx/panopticon`, `@brnyxx/panopticon-linux-x64-gnu`, `@brnyxx/panopticon-linux-arm64-gnu`, `@brnyxx/panopticon-darwin-x64`, and `@brnyxx/panopticon-darwin-arm64`. The root package declares exact-version optional dependencies on the four native packages. The supported npm-native targets are GNU Linux x64/arm64 and macOS x64/arm64 only. Schema `1.0` remains unchanged and `[project].version` remains the sole release-version authority.
- **Native-only launcher.** npm packages are assembled from the four retained native archives. The root launcher has no lifecycle scripts, postinstall download, network operation, persistence, or Python wrapper/import; it executes only the installed matching retained binary. The installer boundary is separate from `pano --offline`, which remains the product-wide outbound-path boundary.
- **One bundle, exact assets.** Rehearsal creates and signs `brnyxx-panopticon-<version>.tgz`, `brnyxx-panopticon-linux-x64-gnu-<version>.tgz`, `brnyxx-panopticon-linux-arm64-gnu-<version>.tgz`, `brnyxx-panopticon-darwin-x64-<version>.tgz`, and `brnyxx-panopticon-darwin-arm64-<version>.tgz`, with an SBOM for each, in the existing signed build-once bundle. A scripts-disabled, offline local npm install of root plus the matching platform tarball proves no registry fallback and runs `pano version`.
- **Promotion and recovery.** Production and recovery download the retained npm artifact set; they never rebuild, overwrite, or substitute it. A GitHub-hosted Node >=22.14/npm >=11.5.1 job in the protected `npm` environment uses trusted OIDC publishing. It checks existing registry versions for exact retained-artifact integrity, fails on a mismatch, publishes/verifies all platform packages before the root, and makes GitHub publication depend on both PyPI and npm. Initial package creation is a documented human 2FA bootstrap using these exact artifacts; all subsequent trusted publication is OIDC-only.
- **Novice first-run path.** Root help and terminal `doctor` output provide bilingual next-command guidance without changing JSON, result status, reason code, diagnostics, exit semantics, or command registration order. The pinned public path is `uv tool install panopticon-mcp==1.0.2` → `pano doctor --offline` → `pano watch SERVER_NAME --offline`. Mirrored EN/KO guides own prerequisites, installation, observation, result interpretation, commands, artifacts, cleanup, and troubleshooting; a dedicated agent guide owns JSON, exit-code, confirmation, and reporting contracts.
- **Offline image bootstrap.** Docker and Podman runs preflight the exact image reference and always use the runtime no-pull policy; a missing image fails before target execution with `IMAGE_NOT_PRESENT`. The EN/KO guides provide a separately authorized, digest-pinned GHCR staging procedure for all four runtime images, and privacy documentation lists connected image resolution/pull explicitly.
- **Authoritative cleanup.** Interactive runtime cleanup attempts graceful attach and container stops, then treats successful force removal as the authoritative no-orphan result. A failed force removal remains `CLEANUP_FAILED`; a transient graceful-stop error followed by successful removal does not downgrade otherwise complete evidence.
- **Release ref provenance.** Every release channel is job-gated to `refs/heads/main`; production and recovery preflight additionally reject a retained rehearsal whose `headBranch` is not `main`. A documented `--ref main` invocation is guidance, never the enforcement control.
- **Release artifact reproducibility.** The two Python candidate builds use separate directories outside the source tree, compare wheel and sdist bytes, and copy only a matched candidate into the retained artifact set. A first build can never contaminate the second build's source manifest.
- **Registry propagation.** TestPyPI and PyPI verification retry only a version-specific metadata `404` for a bounded 60-second window after upload, then require exact retained hashes. Every other HTTP error and exhausted propagation window fails closed.
- **Bilingual static demo.** A dependency-free EN/KO landing page demonstrates one fixture-backed observation, keeps incomplete and unsupported coverage visible, and provides keyboard-accessible copy and evidence controls. Progressive sections expose verified installation choices, prerequisites, a side-effect-aware command map, agent operating boundaries, and canonical design/usage links without executing product commands in the browser. A standard-library deterministic builder validates locale parity and produces the two routes; a least-privilege, SHA-pinned GitHub Pages workflow deploys generated artifacts with no product analytics, browser storage, or runtime remote resources.

### Interfaces
- `scripts/package_npm.py --archives-dir <retained-archives> --output-dir <npm-dist>` — creates the five versioned tarballs from retained native archives.

### Tests
- The release manifest rejects a missing, extra, or renamed npm tarball or SBOM.
- A scripts-disabled offline local install of root and each matching platform tarball has no registry fallback and executes the retained binary.
- Existing npm versions pass only when registry integrity equals the retained tarball; a mismatch, a root-before-platform attempt, or an unavailable retained artifact blocks promotion/recovery.

### Definition of done
- The signed rehearsal bundle, production/recovery workflow, and release manifest enumerate the same five npm tarballs. All five scoped packages are public from those exact retained bytes, registry integrity matches the signed bundle, and clean `npm install` plus `npx` checks execute `pano version` on every supported target. The matching PyPI patch files are the exact rehearsed files. Standard self-scan, protected-environment preflight, bilingual onboarding, localized CLI guidance, deterministic two-route demo build, keyboard/mobile browser QA, and the existing E19 gates pass on the release commit. npm retains the four-target GNU/macOS boundary and contains no Python launcher, install script, or runtime network/persistence path. npm recovery is non-atomic but exact-integrity, platform-first, and root-last; schema `1.0` and the existing E19 release guarantees remain unchanged.
