# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Delegated: zero-dependency static HTML, CSS, and browser JavaScript served from GitHub Pages. The
site must not add a package dependency, runtime backend, account system, analytics, or telemetry.
The public URL remains an open release decision until repository Pages settings and a deployment
run provide evidence.

## Users

The primary user is a beginner or "vibe coder" who has installed or is considering an MCP server
but does not have security or container expertise. They need to understand what Panopticon observes,
verify that it is installed, find one configured MCP, run a first observation, and interpret
incomplete evidence without guessing.

The secondary user is an MCP author who needs a clear route from the landing page to `pano scan`
and CI guidance. The first-run experience prioritizes the installer because the observe line is the
face of the product.

## Product Purpose

Panopticon helps people inspect what an MCP server actually does. It discovers configured MCPs,
observes a selected server in a decoy-filled isolated environment, records file, network, process,
and leak evidence, and explains declared-versus-observed differences.

The new demo experience succeeds when a newcomer can move from the landing page to a verified
installation and a first `doctor` or `watch` result without needing to understand the full command
surface first.

## Positioning

Panopticon is a local-first behavior observatory, not a rating site. Its differentiating mechanism
is executing MCP tools against decoy data inside an isolated environment and retaining explicit
coverage and observation evidence. It does not turn missing evidence into a verdict.

## Operating Context

- Discovery begins on GitHub, PyPI, or the static introduction site.
- First use happens in a terminal through `uvx` or a persistent install.
- `pano version` verifies the installed release.
- `pano doctor` discovers supported AI client configuration without requiring Docker or Podman.
- `pano watch SERVER_NAME --png` requires Docker or Podman for local observation.
- `pano explain RULE_ID` helps the user interpret one finding.
- MCP authors use `pano scan` and `pano ci` as a separate route.
- The demo exposes validated public install choices, exact runtime prerequisites, one bounded
  observation, a goal-oriented command map, and an agent protocol without executing commands in the
  browser.
- Human guides own installation, first observation, result interpretation, artifacts, cleanup, and
  troubleshooting in English and Korean. A separate agent guide owns JSON, exit, confirmation, and
  reporting contracts. Maintainer release mechanics do not share the novice path.

## Capabilities and Constraints

- Preserve the exhaustive statuses `COMPLETE`, `PARTIAL`, `INCOMPLETE`, `FAILED`, `UNSUPPORTED`,
  `SKIPPED`, and `NOT_REQUESTED`; user copy must keep the `UNKNOWN` conclusion visible.
- Never publish a numeric risk score or a certification verdict.
- Never add telemetry, analytics, accounts, automatic uploads, or a public observation catalog.
- Do not send real secrets, home paths, or observation artifacts from the website.
- The website is an explanatory and activation surface; it does not execute an MCP in the browser.
- English and Korean experiences must expose the same information and actions.
- The repository and latest public PyPI, npm, GitHub, and Homebrew release verified on
  2026-08-31 are 1.0.2: <https://pypi.org/pypi/panopticon-mcp/1.0.2/json>.
- Configuration changes remain dry-run, confirm, backup, apply, re-check, and undo operations.
- Copyable shell examples use `SERVER_NAME` or `RULE_ID`, never angle-bracket placeholders that a
  shell can interpret as redirection.
- The canonical first runtime path uses `pano doctor --offline` and
  `pano watch SERVER_NAME --offline`; installer traffic remains a separate boundary.

## Brand Commitments

- Product name: Panopticon.
- CLI name: `pano`.
- Tagline: "We don't watch you. We watch your MCPs."
- Existing logo and hero assets under `.github/assets/` remain source material.
- Existing brand language is direct, technical, evidence-led, and avoids fear-based claims.

## Evidence on Hand

- The production CLI and its command contracts live under `src/panopticon/`.
- The current public onboarding is `README.md` and `docs/README.ko.md`.
- `.github/assets/logo.svg`, `.github/assets/hero.svg`, and `.github/assets/panopticon.png` are real
  product assets.
- `scripts/manual_qa.py` exercises the shipped help, version, doctor, explain, watch, PNG, and core
  end-to-end surfaces.
- `docs/PRODUCT_READINESS.md` records current release evidence and unresolved publication work.
- There are no verified testimonials, customer counts, usage metrics, benchmark comparisons, or
  case studies available for the landing page. Future work must not invent them.

## Product Principles

1. Show the first useful action before the complete feature list.
2. Explain evidence and coverage in plain language without weakening their meaning.
3. Keep the default path local, private, and reversible.
4. Use real commands, real states, and checked fixture output instead of marketing claims.
5. Give every blocked or incomplete state one concrete next action.

## Accessibility & Inclusion

The introduction site must support keyboard operation, visible focus, reduced motion, zoom, narrow
mobile layouts, and English/Korean text expansion. Technical identifiers remain unlocalized, while
explanatory copy uses plain language for users without security or container experience.
