# SENT-009 — Oversized argument accepted

## Problem
A tool accepts, hangs, or crashes when given a grossly oversized argument. The dynamic probe tests whether argument-size limits are enforced before the handler runs.

## Impact
Unbounded input can consume memory or CPU, stall a worker, or terminate a service. The observed behavior depends on the selected tool, its schema, and the isolated probe runtime.

## Evidence
The dynamic prober selects a schema-compatible string, array, or object field and sends the exact marker `__SENTINEL_OVERSIZED__`, expanded to a 1,048,576-character payload (or an array/object containing that payload). A non-error response produces SENT-009 evidence; a timeout after session initialization is also recorded as evidence. Responses are sanitized and capped at 16,384 UTF-8 bytes, and requests and logs are retained in bounded form.

## Recommended action
Enforce schema and byte-size limits before invoking tool handlers. Reject oversized values deterministically and keep resource limits independent of downstream handler behavior.

## How to verify
Run the dynamic scan in its isolated Docker probe environment. SENT-009 evidence should not be emitted when the selected field rejects the oversized value or returns a bounded error without hanging or crashing.

## Limits
This is bounded runtime evidence, not a guarantee for every input size, field, tool, deployment, or concurrency level. The campaign runs each approved probe once in a fresh session, uses only schema-compatible fields and inert baseline arguments, and has a 20-second per-probe timeout within a 120-second campaign budget. Unlisted tools, unsupported schemas, aliases, alternate transports, and unscanned code are outside coverage; no verdict about overall service safety is implied.
