# WATCH-001 — Decoy value exfiltrated

## Problem
A decoy secret placed in the sandbox (a fake token in a file or environment variable) appeared in outbound traffic, a written file, a process argument, or stderr during a tool call.

## Impact
The server read a credential it was not given for its task and sent it somewhere. If it does this with decoys it will do it with real credentials.

## Evidence
`spans[*].events[kind=leak]` with `decoy_key` and `sink` (host:port or path).

## Recommended action
Remove the server from your client config until the maintainer explains the behavior. If you must keep it, run it only through `pano wrap` and never pass real tokens in `env`.

## How to verify
`pano watch <name>` again; the `leak` event must be absent in every span.

## Limits
TLS payloads are not inspected; leaks over TLS to a declared host are not detectable by this rule (see WATCH-003 for undeclared hosts).
