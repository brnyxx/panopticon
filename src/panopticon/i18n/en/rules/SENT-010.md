# SENT-010 — Injection payload executed

## Problem
A tool argument causes the Sentinel scratch-canary side effect during a dynamic probe. This rule identifies execution of an injection string supplied as tool data.

## Impact
If argument text is interpreted as code or a command, an attacker may trigger unintended actions with the tool's privileges. The canary observation concerns only the probe's local scratch path and does not establish impact in other environments.

## Evidence
The prober selects a schema-compatible string field and submits the exact marker `__SENTINEL_INJECTION__`, which is replaced at execution time by a payload that touches the isolated Sentinel canary path. SENT-010 evidence is emitted only when the canary exists after the call. Responses and logs are sanitized and response evidence is bounded to 16,384 UTF-8 bytes.

## Recommended action
Treat tool arguments as inert data: remove dynamic evaluation and command construction, use parameterized APIs, and apply strict schema validation before handler execution. Keep probe canaries isolated from production state.

## How to verify
Run the dynamic scan in the isolated Docker probe environment and inspect the bounded dynamic evidence. SENT-010 evidence should not be emitted when the marker remains data and the scratch canary is not created.

## Limits
This is a single, bounded canary observation, not proof that every injection variant is blocked or that arbitrary code execution occurred elsewhere. Each approved probe runs once in a fresh session, with schema-compatible fields, inert baseline arguments, sanitized logs, a 20-second per-probe timeout, and a 120-second campaign budget. Only the local canary side effect is checked; other sinks, tools, transports, aliases, concurrency, and unscanned code are outside coverage, and no overall security verdict is implied.
