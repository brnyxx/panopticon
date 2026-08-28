# WATCH-013 — Read-only hint contradiction

## Problem
A tool marked read-only performed a file write or client-visible network POST.

## Impact
Observed behavior contradicts the tool annotation used by clients and reviewers.

## Evidence
Write or POST evidence is attributed to the annotated tool-call span.

## Recommended action
Remove the mutation or correct the annotation and declaration.

## How to verify
Repeat the call and confirm no write or visible POST occurs under the read-only hint.

## Limits
Opaque TLS activity cannot confirm a POST body and is reported as `UNKNOWN`.
