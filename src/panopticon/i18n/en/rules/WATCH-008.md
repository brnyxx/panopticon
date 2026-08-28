# WATCH-008 — Undeclared external process

## Problem
A tool launched an external process outside its authoritative declaration.

## Impact
The observed process expands execution beyond the attributed tool scope.

## Evidence
Process evidence records the executable basename, arguments classification, and span.

## Recommended action
Remove the subprocess or declare the exact executable and purpose.

## How to verify
Repeat the call and compare every non-tooling executable with the declaration.

## Limits
Exact interpreter and package-tool exclusions remain visible; incomplete process coverage yields `UNKNOWN`.
