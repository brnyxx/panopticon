# HIST-003 — Npm maintainer transition

## Problem
The npm maintainer set changed between two complete snapshots.

## Impact
Package publication authority has changed.

## Evidence
The finding records normalized added and removed maintainer identities.

## Recommended action
Confirm the change through the package repository and registry.

## How to verify
Refresh npm history and run `pano doctor`.

## Limits
This rule requires two fresh npm snapshots.
