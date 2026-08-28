# SENT-002 — Unsafe execution from tool input

## Problem
Input controlled by a tool reaches an unsafe execution or deserialization sink. The static Semgrep rule traces a typed or untyped MCP tool parameter to `eval`, `exec`, `pickle.loads`, `yaml.load`, or a shell-enabled `subprocess.run`, `subprocess.call`, or `subprocess.Popen`.

## Impact
If an input value reaches one of these sinks, a caller may influence code execution, deserialization, or shell command interpretation along that path. The impact depends on the reachable path and the sink's runtime behavior.

## Evidence
The Semgrep rule `sentinel.sent002.unsafe-execution` uses taint analysis on Python MCP tool functions. Its source patterns are parameters of synchronous or asynchronous functions decorated with an MCP tool decorator; its sink patterns are the execution and deserialization calls listed above. A finding records the matched source-to-sink location.

## Recommended action
Replace dynamic execution with explicit parsers and fixed command allowlists.

## How to verify
Run `pano scan <path>` again. The SENT-002 finding should be absent when no MCP tool parameter reaches one of the configured sinks in the scanned Python source.

## Limits
This is static taint evidence, not an observation of a tool call and not proof that an input was exploited. The rule covers only its configured Python patterns; indirect flows, other languages, runtime-generated code, and sinks outside those patterns may not be detected.
