# Architecture

See `panopticon-buildplan.md §3` for the epic graph, `AGENTS.md` for layout and code standards, and `docs/DECISIONS.md` for the frozen contracts this file summarizes.

## The pipeline

```
pano watch <server>
  inventory.get(installation_id)
    -> sandbox.prepare(image_digest, decoy_home)   E05, E06
    -> probe.start(server)                         E08   modern metadata or legacy handshake
    -> for tool: span = tracer.begin(tool, index)  E07
                 probe.call(tool, gen_args)
                 events = tracer.end(span)
    -> declared.extract(server)                    E10
    -> analyzers.behavior.run(events, declared)    E12   -> findings
    -> observation = Observation(...)              §21
    -> store.write(observation)                    E01   canonicalize + leak check + atomic replace
    -> baseline.store(observation)                 E14
    -> reporters.render(sanitized_view)            E17
```

Every stage returns a structured result. No stage raises across an epic boundary.

## Typed core spine

The spine exists before any feature epic, because identity, state, and persistence choices are irreversible once real artifacts exist on disk.

- **`models/`**: branded ID types, immutable Pydantic v2 persistence-boundary models, exhaustive stage/status/reason variants, coverage dimensions, protocol era, and schema metadata. No raw dictionary crosses a boundary.
- **`store/`**: the only writer of persisted artifacts.
- **`util/canonicalize.py`**: versioned canonical serialization, used for both persistence and comparison.
- **`engine/`**: pipeline contracts for doctor, watch, diff, and scan, plus the boundary `Result` and diagnostics types.
- **`cli/`**: parsing and rendering only; it holds the exit-code precedence table and nothing else.

## Identity

Two identities, deliberately distinct:

| Identity | Grain | Definition | Used for |
|---|---|---|---|
| `server_id` | group | `npm:<pkg>`, `pypi:<pkg>`, `github:<owner>/<repo>`, `docker:<image>`, `remote:<host>[/<path>]`, `local:<sha256(command+args)[:12]>` | grouping in reports, registry history lookup, arg-generation seed |
| `installation_id` | one config entry | stable hash of `client \| normalized config path \| scope \| JSON pointer \| entry name` | observations, baselines, wrap records, suppressions, fixes, diff joins |

The same package installed in three clients has one `server_id` and three `installation_id` values. Entries are never merged. `identity_confidence: low` (local commands) never merges and never compares across entries.

Findings carry a third identity:

- `logical_key = rule_id | installation_id | subject`, stable across runs, so diff can classify a finding whose evidence changed as `CHANGED` instead of `RESOLVED` plus `NEW`.
- occurrence id = hash including normalized evidence, addresses one concrete instance.

Spans carry `span_id = tool + call_index`, monotonic and tracer-visible, so event attribution is deterministic across repeat runs.

## State and coverage

A stage never reports a bare string. Each stage result carries:

- **status**, exhaustive: `COMPLETE | PARTIAL | INCOMPLETE | FAILED | UNSUPPORTED | SKIPPED | NOT_REQUESTED`.
- **reason_code**: stable, machine-consumed, explaining why the status is what it is (timeout, runtime unavailable, destructive skip, legacy fallback, buffer overflow, and so on).
- **coverage**: explicit dimensions (file, net, process, dns, proxy, snapshot, stdio) each with their own status.

Rules read coverage before they conclude. Absent evidence under complete coverage is a negative result; absent evidence under anything else is `UNKNOWN`. Nothing collapses `UNKNOWN` into a pass, and no reporter, badge, or diff category may do so either.

The legacy-only handshake stage is `NOT_REQUESTED` for a modern run; modern version discovery is its own stage. That distinction is what makes two runs of different eras comparable.

## Schema lifecycle

Persisted schemas develop on the **0.x** line. Every breaking shape change bumps the version within 0.x and ships an idempotent migrator dispatched explicitly by source version. Shipped JSON Schemas are generated and validated from the runtime models, never hand-maintained beside them.

Schema `1.0` was frozen exactly once at the 0.9 release-candidate gate, together with the ID
formats, stage reason codes, event/finding/baseline/diff/wrap shapes, the canonicalizer version,
the CLI exit codes, and the `_pano_original` v1 representation. Post-1.0 breaking changes are 2.0
and need their own release plan.

## Persistence, canonicalization, and the leak boundary

Every cache, observation, baseline, finding, wrap record, alert, journal entry, backup, log artifact, and every JSON, SARIF, Markdown, PNG, and SVG output passes through one path:

```
typed model
  -> normalization (~-relative paths, lowercase hosts, UTC ISO-8601 times)
  -> versioned canonical serialization
  -> LeakContext scan            mandatory, no bypass
  -> restrictive temp write in the destination directory
  -> flush + fsync
  -> symlink-safe atomic replace
  -> directory fsync where the platform supports it
```

The leak scan matches raw, escaped, URL-encoded, form-encoded, base64, and chunk-split variants, plus native and WSL home path forms. Render models are sanitized before binary compression, so PNG and SVG bytes cannot smuggle values that the JSON path rejected.

An AST checker fails the build on any direct write outside `store/` and the approved config-patch modules. Canonical semantic comparison ignores only the approved volatile fields (timestamps, PIDs, durations, container IDs); run metadata is compared separately, so determinism tests can't be satisfied by hiding a real difference.

## Secrets

`SecretStore` is a typed protocol with macOS Keychain, Linux Secret Service, and native Windows Credential Manager backends and a deterministic in-memory fake for tests. Encryption keys live in the credential store; secret-bearing config backups are encrypted with authenticated encryption. If no backend is available, the operation returns a typed guidance-only result and writes nothing: no plaintext `.env`, no token file, no key file, no unencrypted secret-bearing backup.

## Protocol eras

The probe is a dual-era client.

| Era | Lifecycle | Transports |
|---|---|---|
| modern (`2026-07-28`) | per-request metadata, server discovery, version retry | stdio, Streamable HTTP |
| legacy | `initialize` + `notifications/initialized`, session-based | stdio, Streamable HTTP, deprecated HTTP+SSE |

Era selection is cached per transport and every observation records the requested version, the selected version, the era, and the typed fallback reason. Desynchronized streams are not resumed after a timeout; they end with a typed transport error.

## Network exceptions

Panopticon is local-first. Three outbound destinations exist and each is enumerated in `docs/privacy.md`:

1. Package registries, for release and maintainer history.
2. Whatever the observed MCP itself contacts, inside the sandbox, through the logging proxy.
3. The semantic analyzer in `scan --mode deep`: user-invoked, user-keyed, disclosed before the first request, redacted, and disabled by `--offline`, in which case semantic results are typed `UNSUPPORTED` and the scan is `INCOMPLETE`.

There is no telemetry, no crash reporting, no update ping, and no upload path.

## Dependency direction

`cli → engine → *`. `analyzers → findings, rules`. `probe → sandbox`. `diff → baseline, findings`. `reporters` read the sanitized render model only. `store` is imported by everything that persists and imports no feature package. `sandbox` and `wrap` do not import each other. Boundaries are `Protocol`s: `Runtime`, `ClientAdapter`, `Extractor`, `Reporter`, `SecretStore`, `Clock`, `Http`.

Collectors return results with a state instead of raising across epics, and `cli/` renders those states rather than interpreting them.
