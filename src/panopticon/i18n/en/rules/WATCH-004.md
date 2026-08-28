# WATCH-004 — Idle network activity

## Problem
Network activity occurred in the reserved idle span between tool calls.

## Impact
The server communicated without an active tool-call attribution.

## Evidence
Network evidence is attributed to the `__idle__` half-open span.

## Recommended action
Disable background traffic or document and isolate the required endpoint.

## How to verify
Observe an idle window again and confirm no network event is attributed to it.

## Limits
Incomplete span or network coverage yields `UNKNOWN`.
