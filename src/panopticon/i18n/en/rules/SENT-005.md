# SENT-005 — Hardcoded secret

## Problem
Source or configuration contains a credential-shaped value that matches a provider signature or a contextual, high-entropy secret pattern. The finding identifies a candidate embedded in the scanned file rather than a value loaded at runtime.

## Impact
A credential committed in source or configuration can be copied, logged, or packaged with the application and may permit access if it is active. Actual validity, scope, and exposure are not established by this static finding.

## Evidence
The Semgrep rules `sentinel.sent005.provider-secret-candidate` and `sentinel.sent005.secret-candidate` select provider-shaped strings (`sk-`, `ghp_`, `github_pat_`, `xox[baprs]-`, `AKIA`, or `AIza`) and assignments such as `api_key`, `secret`, `token`, or `password` followed by at least 20 allowed characters. The detector rescans candidate Python and configuration files, keeps provider matches or contextual values with Shannon entropy at least 4.5, and reports a redacted snippet plus a SHA-256 fingerprint. A configured path-and-fingerprint allowlist and reserved `sk-test-` values under `tests/fixtures/` or `demo/` are exempted.

## Recommended action
Load credentials from an external secret store or environment at runtime. Remove the embedded value, rotate it when exposure is possible, and use the reported fingerprint to review allowlist entries without putting the secret back into logs or source.

## How to verify
Run `pano scan <path>` again after removing or rotating the embedded value. The SENT-005 finding should be absent when no scanned candidate matches the provider or contextual high-entropy checks, or when an intentionally reserved test value is covered by the documented exemption.

## Limits
This is static text and entropy evidence, not confirmation that a credential is valid, active, or used. Detection is limited to scanned Python/configuration files and the listed signatures, contextual assignments, entropy threshold, allowlist, and reserved test paths; obfuscation, concatenation, generated files, other credential formats, and unscanned files may not be detected. Redaction prevents the finding from disclosing the matched value.
