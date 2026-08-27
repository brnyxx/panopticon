# Coordinated disclosure policy (project publications)

Applies when the Panopticon project publishes observations about third-party MCP servers. The tool itself publishes nothing.

1. **Contact**: GitHub Private Vulnerability Reporting on the affected server's repository, the same intake `SECURITY.md` publishes for Panopticon (DECISIONS #14). It is the sole official channel; no maintainer email address and no private issue request is offered or published. Where the observed project has no such form, the observation waits until its maintainers open one.
2. **Embargo**: WATCH-001 (leak) 30 days; all other findings 14 days.
3. **No response**: publish facts only after embargo — observation JSON, reproduction command, no speculation on intent.
4. **Emergency**: immediate publication only if active exploitation is already public.
5. **Never published**: exploitation techniques, decoy-generation internals.
6. **Maintainer response** is published verbatim with consent, and a `.panopticon.yaml` self-declaration is offered as the fix path.
