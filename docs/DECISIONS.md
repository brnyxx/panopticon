# Decisions

Numbered, append-only. Format: context / options / chosen / why.

## 1. Container image registry org
- Context: E05 needs a home for `pano-sandbox-*` images (panopticon-buildplan.md §8).
- Options: `ghcr.io/<personal>`, `ghcr.io/<org>`, Docker Hub.
- Chosen: **TBD**
- Why:

## 2. Initial network allowlist
- Context: WATCH-003/005 need an install-time allowlist (panopticon-buildplan.md §15).
- Chosen: the list in `analyzers/behavior/allow.yaml` (registry + GitHub release CDN only). Revisit when a fixture shows a false positive.

## 3. `wrap` OS notification default
- Chosen: off. Alerts are surfaced by the next `pano doctor`. `--notify` opts in.

## 4. Host wildcard syntax in `.panopticon.yaml`
- Chosen: leading `*.` only (`*.example.com`). No mid-label globs. Matches allow.yaml semantics.

## 5. PNG card design
- Chosen: **TBD** before E17.
