# WATCH-009 — Broad file enumeration

## Problem
A call statted or read at least ten distinct paths under personal-content directories.

## Impact
The observed pattern enumerated a broad collection rather than a narrow requested path.

## Evidence
Distinct normalized paths and operations are counted within the attributed span.

## Recommended action
Limit traversal to the explicit input path and avoid recursive discovery by default.

## How to verify
Repeat the call and confirm the distinct-path count stays below the documented threshold.

## Limits
The threshold is ten; incomplete file coverage keeps a below-threshold result `UNKNOWN`.
