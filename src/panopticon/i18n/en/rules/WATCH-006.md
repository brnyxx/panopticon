# WATCH-006 — Undeclared personal config read

## Problem
A tool read a personal shell, Git, or application config file outside declared scope.

## Impact
The server accessed user-specific settings unrelated to the attributed tool scope.

## Evidence
Read evidence records the normalized config path, tool, and span.

## Recommended action
Remove the read or narrow it to explicit synthetic configuration.

## How to verify
Repeat the call and confirm the personal config path is not read.

## Limits
Stat-only evidence is distinct from a read; incomplete tracing yields `UNKNOWN`.
