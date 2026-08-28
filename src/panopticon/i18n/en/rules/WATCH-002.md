# WATCH-002 — Undeclared decoy file read

## Problem
A tool read a credential decoy file outside its declared path scope.

## Impact
The observed read exceeds the scope attributed to that specific tool.

## Evidence
File-read events identify the path, span, tool, and declaration match result.

## Recommended action
Remove the unnecessary read or declare the exact path and purpose for the affected tool.

## How to verify
Run `pano watch <name>` and confirm the read is removed or matched by authoritative scope.

## Limits
Incomplete file tracing reports `UNKNOWN`; an open or stat without a read is not enough.
