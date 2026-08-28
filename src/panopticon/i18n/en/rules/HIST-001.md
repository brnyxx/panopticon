# HIST-001 — New release observed

## Problem
At least one release appeared after the comparison snapshot.

## Impact
The configured package may have a newer version available.

## Evidence
The finding records normalized release versions.

## Recommended action
Review release notes before changing the pin.

## How to verify
Run `pano doctor` with fresh registry history.

## Limits
Release presence does not describe runtime behavior.
