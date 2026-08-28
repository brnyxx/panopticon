# WATCH-010 — Declared and observed scope match

## Problem
This informational condition is available only when authoritative declarations cover every observed item.

## Impact
It records a complete comparison boundary without assigning a security verdict.

## Evidence
All applicable source coverage is complete and every path, host, and process matches tool-specific scope.

## Recommended action
Keep declarations current and preserve complete observation coverage.

## How to verify
Repeat the observation and confirm every applicable stage remains complete.

## Limits
Any suppression, exclusion, uncovered event, or incomplete stage makes this condition `UNKNOWN` or unmatched.
