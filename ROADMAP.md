# Roadmap

Versions advance by closed epics, never by dates. Full definitions: `panopticon-buildplan.md` (§3 epics, §23 stages). Live status: `docs/PROGRESS.md`.

`0.1` through `0.9` below are internal development and schema milestones — capability checkpoints recording which epics are closed, not promises to publish. None of them ships to a public channel. The first public release in this accepted execution is `1.0.0`, after every release gate has passed. The "result" column therefore states what the capability does once its epics close, not what is available for download.

| Version | Closes | Capability once closed |
|---|---|---|
| 0.1 | E01–E04, E11, E12 (CFG/HIST), E17 (terminal/json) | `pano doctor` — discovery, config checks, release history since last look |
| 0.2 | E05–E08, E10, E12 (WATCH), E18 (ko) | `pano watch` — sandboxed observation, declared-vs-observed |
| 0.3 | E13, E14 | `pano fix`, `pano diff`, baselines |
| 0.4 | E15 | `pano wrap`, `pano install` |
| 0.5 | E09, E17 (PNG/badge/Markdown) | remote MCPs, share card, badge |
| 0.6 | E16 | `pano scan`, GitHub Action, upstream replay restored |
| 0.7 | E18 (en), all 6 clients, WSL2 | multilingual, every client |
| 0.8 | E19 (binaries, brew, signing, SBOM) | every install path |
| 0.9 | §22 quality bar, schema 1.0 frozen, docs complete | release candidate |
| **1.0.0** | §2 checklist in full | — |

## After 1.0
- eBPF tracer (privilege permitting)
- macOS `wrap` file observation (EndpointSecurity)
- TypeScript AST static analysis
- Optional public dataset export of observations
- Organization features (private inventory, policies, alert channels)

## Explicit non-goals (any version)
Safety scores, "Safe/Certified" badges, telemetry, SaaS, exploitation of third-party services.
