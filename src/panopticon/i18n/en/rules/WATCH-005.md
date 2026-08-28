# WATCH-005 — Unexpected install host

## Problem
The installation span contacted a non-registry host.

## Impact
Installation performed network activity beyond the recognized package source.

## Evidence
The normalized host is recorded in the `__install__` span with allowlist classification.

## Recommended action
Pin dependencies and remove installation hooks that contact unrelated hosts.

## How to verify
Rebuild in an empty cache and inspect every installation-span destination.

## Limits
Recognized registries are retained as excluded evidence; incomplete traffic capture yields `UNKNOWN`.
