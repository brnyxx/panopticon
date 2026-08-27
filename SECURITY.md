# Security Policy

## Reporting a vulnerability in Panopticon

Use **GitHub Private Vulnerability Reporting** on `brnyxx/panopticon`: open the repository's **Security** tab and choose **Report a vulnerability**. That form is the only official intake. We don't publish a security mailbox, because an unmonitored address is worse than none.

We acknowledge within 3 business days. Please include the command you ran, the `pano` version, your OS and container runtime, and the sanitized output. Never attach real tokens, real config files, or `--real-env` values: Panopticon's own output is already leak-checked, so the artifacts it wrote are the right thing to send.

## Reporting a finding *about an MCP server* observed with Panopticon

Panopticon reports facts about what a server did. If you believe an observation is wrong, open a public issue with the observation JSON and the reproduction command. If you are the server's maintainer, add a `.panopticon.yaml` self-declaration (`docs/self-declaration.md`) so future observations compare against it.

Project publications about third-party servers follow `docs/disclosure.md`.

## What we treat as a vulnerability in Panopticon

- Any persisted or rendered artifact containing a real token, a real home absolute path, a `--real-env` value, or plaintext Panopticon-managed secret material.
- Sandbox escape, host filesystem access beyond the explicit `--self` read-only source mount, or egress that bypasses the logging proxy.
- A config write that loses user data, escapes the fix/install journal, or cannot be undone.
- Any path that reports observed behavior as complete when coverage was partial, unsupported, skipped, timed out, or failed.

## Supply chain

Release artifacts are signed with Sigstore and ship an SBOM and provenance. Sandbox images are pulled by digest from `ghcr.io/brnyxx`; `sandbox/images.lock` holds the registry-resolved digests, and the runtime trusts digests rather than tags. Report signature, digest, or provenance mismatches through the same private reporting form.

## Outbound network use

Panopticon talks to package registries for history lookups and, inside the sandbox, carries the observed MCP's own traffic through a logging proxy. One additional destination exists and only when you ask for it: `scan --mode deep` sends redacted source excerpts to the model provider using **your** API key, after printing what will be sent. `--offline` disables every outbound call. Full inventory: `docs/privacy.md`.
