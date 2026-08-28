# WATCH-014 — Startup network activity

## Problem
Network activity occurred in the reserved startup span before protocol readiness.

## Impact
The server communicated before a tool call or completed handshake could own the event.

## Evidence
Network evidence is attributed to the `__startup__` half-open span.

## Recommended action
Remove the startup beacon or explicitly isolate required bootstrap traffic.

## How to verify
Start the server again and confirm the startup span contains no network event.

## Limits
Incomplete startup-span or network coverage yields `UNKNOWN`.
