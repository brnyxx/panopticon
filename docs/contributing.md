# Contributing

Start with `AGENTS.md` (workflow, standards) and `docs/PLAN.md` (what to build).

- Pick the lowest open epic whose dependencies are closed (`docs/PROGRESS.md`).
- Adding a rule / adapter: see the checklists in `AGENTS.md`.
- Run `make ci` before pushing.
- PRs use `.github/PULL_REQUEST_TEMPLATE.md`; changes to behavior must update `docs/PLAN.md` in the same PR.
