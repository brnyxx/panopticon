# Known limitations

Maintained as the source of truth for the "Limits" sections in rule docs and for README. Every observation report prints the relevant subset.

- **TLS is not inspected.** Leaks over TLS to a *declared* host are invisible to WATCH-001. Undeclared hosts are still caught (WATCH-003).
- **Time- or condition-triggered behavior** is only caught if it fires inside the `__idle__` window (default 10 s).
- **Tools that need real APIs** may error in the decoy environment; behavior up to the error is still recorded.
- **macOS `wrap`** records network targets by polling; file access is `UNSUPPORTED`.
- **Windows** native sandbox is unsupported; use WSL2.
- **Remote (HTTP/SSE) servers**: only the client-visible side is observed; `file` stage is always `UNSUPPORTED`.
- **An observation is one run.** "Did" is not "always does" / "never does".
- **Declared scope** inferred from README/descriptions is `PARTIAL`; maintainers can make it `COMPLETE` with `.panopticon.yaml`.
