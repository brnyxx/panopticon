# Architecture

See `docs/PLAN.md §3` for the epic graph and `AGENTS.md` for layout and dependency direction.

```
pano watch <server>
  inventory.get(server)
    -> sandbox.prepare(image, decoy_home)       E05, E06
    -> probe.start(server)                      E08   initialize, tools/list
    -> for tool: span = tracer.begin(tool)      E07
                 probe.call(tool, gen_args)
                 events = tracer.end(span)
    -> declared.extract(server)                 E10
    -> analyzers.behavior.run(events, declared) E12   -> findings
    -> observation = Observation(...)           §21
    -> util.leak_check.assert_clean(...)        always
    -> baseline.store(observation)              E14
    -> reporters.render(observation)            E17
```

Boundaries are `Protocol`s: `Runtime`, `ClientAdapter`, `Extractor`, `Reporter`. Collectors return results with a state (`COMPLETE | PARTIAL | INCOMPLETE | FAILED | UNSUPPORTED`) instead of raising across epics.
