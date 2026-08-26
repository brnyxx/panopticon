# Privacy

## What leaves your machine
| When | Destination | What |
|---|---|---|
| `doctor`, `diff` (HIST rules) | registry.npmjs.org, pypi.org, api.github.com | package names only |
| `watch` / `scan --mode deep` | package registries (inside the sandbox) | package install traffic |
| `watch` | wherever the *MCP under test* connects (inside the sandbox, via the logging proxy) | whatever the MCP sends — with decoy values, never your real ones unless you pass `--real-env` |
| `scan --mode deep` | OpenAI API (only if `OPENAI_API_KEY` is set and you chose deep) | redacted source excerpts; shown to you before sending |

Nothing else. No telemetry, no crash reports, no update pings. `--offline` disables all of the above.

## What is stored locally
`~/.panopticon/` (0700): observations, baselines, wrap logs, env files (0600), cache, journal. Every file passes `util.leak_check` before it is written: no raw tokens, no absolute home paths, no `--real-env` values.

## What never enters a container
Your home directory, your project files (only their *names* are replicated as empty files), your environment variables (replaced by decoys unless explicitly passed).
