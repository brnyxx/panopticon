# HIST-002 — Major version transition

## Problem
The newest stable release has a higher major version than the prior snapshot.

## Impact
The release may contain incompatible interface changes.

## Evidence
The finding records the old and new major versions.

## Recommended action
Review migration notes before updating.

## How to verify
Refresh registry history and run `pano doctor`.

## Limits
Prerelease and yanked releases are excluded.
