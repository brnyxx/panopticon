# Known limitations

Maintained as the source of truth for the "Limits" sections in rule docs and for the README. Every observation report prints the relevant subset.

## What observation cannot see

- **TLS is not inspected.** Leaks over TLS to a *declared* host are invisible to WATCH-001. Undeclared hosts are still caught (WATCH-003), because the connection target is visible even when the body isn't. Opaque TLS traffic never confirms a POST body.
- **Time- or condition-triggered behavior** is only caught if it fires inside the `__idle__` window (default 10 s).
- **Tools that need real APIs** may error in the decoy environment; behavior up to the error is still recorded.
- **An observation is one run.** "Did" is not "always does" or "never does".
- **Declared scope** inferred from a README or tool descriptions is `PARTIAL`; maintainers can make it `COMPLETE` with `.panopticon.yaml`. Partial inference can name items but never turns unmatched behavior into confirmed behavior.

## Platform coverage

- **Native Windows sandboxing is unsupported.** Use WSL2. Native Windows supports discovery only, and it is verified as its own gate, separate from WSL2.
- **macOS `wrap`** records network targets by polling; file access is `UNSUPPORTED`.
- **Rootless Podman** may attribute some isolation evidence less precisely than rootful Docker. Where the guarantee differs, the state is reported `PARTIAL` rather than assumed equal.
- Local installed commands that cannot be copied into the sandbox or instrumented honestly report `UNSUPPORTED`. They are never run against your real home to make a result appear.

## Remote servers

- **Remote (HTTP/SSE) servers**: only the client-visible side is observed. The `file` stage is always `UNSUPPORTED`, and process coverage is unavailable.
- Legacy HTTP+SSE transport is deprecated upstream. It is supported for compatibility, and the observation records that the fallback happened and why.

## Analysis line

- **TypeScript static analysis** ships as a Semgrep rule set only; AST analysis is post-1.0.
- **Semantic review** (`scan --mode deep`) needs your own API key and network access. Under `--offline`, or without a key, it is typed `UNSUPPORTED` and the scan is `INCOMPLETE`.
- Advisory lookups depend on a cache when offline; a missing cache yields `UNKNOWN`, not a clean result.

## What none of this means

Absent evidence under incomplete coverage is `UNKNOWN`. It is never reported as resolved, never treated as agreement between declared and observed behavior, and never makes an observation badge-eligible.
