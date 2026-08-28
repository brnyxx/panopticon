# SENT-007 — Unverified tool manifest

## Problem
Manifest bytes reach tool registration or loading without a prior trusted integrity check. The rule concerns manifest use that is not preceded by hash or signature verification.

## Impact
An altered manifest could change the tools or permissions presented to the server. This finding is static evidence of a missing verification flow; it does not establish that a manifest was modified or that an attack succeeded.

## Evidence
The AST rule `sentinel.sent007.unverified-manifest` examines top-level Python functions whose name contains `manifest`, or is `load_tools` or `register_tools`. It marks calls to `json.load`, `json.loads`, `yaml.safe_load`, or `yaml.load` when no recognized verification call occurs earlier in that function. Recognized verification calls include `hashlib.sha256`, `hmac.compare_digest`, and methods ending in `.verify`.

## Recommended action
Verify a pinned SHA-256 digest or a trusted detached signature before parsing and using the manifest. Keep `sentinel.integrity.yaml` at version `1`, select exactly one supported mode per manifest (lowercase 64-character SHA-256 or Ed25519, RSA-PSS-SHA256, or ECDSA-SHA256 signature metadata), and keep trust-anchor paths repository-relative.

## How to verify
Add the integrity check before each manifest-load call in the analyzed function, then run `pano scan <path>` again. The SENT-007 match should no longer be emitted for that load when a recognized verification call precedes it.

## Limits
This is static intraprocedural AST evidence, not a cryptographic verification result or runtime observation. It does not prove that the configured digest, key, signature, or algorithm matches the bytes, and it may miss verification hidden behind aliases, helper functions, dynamic dispatch, unsupported APIs, interprocedural flow, or unscanned files. A valid integrity file is loaded for anchor validation, but its entries are not data-flow matched to individual load calls.
