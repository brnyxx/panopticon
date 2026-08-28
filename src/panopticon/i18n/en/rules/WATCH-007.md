# WATCH-007 — Proxy bypass attempt

## Problem
Direct egress was dropped while the sandbox proxy policy was active.

## Impact
The server attempted a route that bypassed the observable proxy path.

## Evidence
Proxy or firewall evidence records a deterministic `DROP` event and destination.

## Recommended action
Route traffic through the configured proxy or remove the direct connection.

## How to verify
Repeat the call and confirm no direct-drop event occurs.

## Limits
A missing proxy log is `UNKNOWN`, not proof that no bypass occurred.
