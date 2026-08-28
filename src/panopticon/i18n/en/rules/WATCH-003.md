# WATCH-003 — Undeclared host connection

## Problem
A tool connected to a host outside its authoritative declared host scope.

## Impact
The server communicated with a destination not attributed to that tool.

## Evidence
Connect, DNS, or client-visible request evidence records the normalized host and span.

## Recommended action
Remove the connection or declare the exact destination and reason for the affected tool.

## How to verify
Repeat the call and compare every observed host with the authoritative declaration.

## Limits
Allowlisted infrastructure remains visible as excluded evidence; incomplete declarations yield `UNKNOWN`.
