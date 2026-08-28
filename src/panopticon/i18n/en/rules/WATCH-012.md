# WATCH-012 — Many external URLs

## Problem
A remote response contained at least ten distinct external URLs.

## Impact
The response exposed a broad set of destinations for follow-up access.

## Evidence
Client-visible response evidence records and counts normalized URL hosts.

## Recommended action
Return only URLs required for the requested result.

## How to verify
Repeat the request and confirm the distinct external URL count is below ten.

## Limits
Opaque or truncated responses keep a below-threshold result `UNKNOWN`.
