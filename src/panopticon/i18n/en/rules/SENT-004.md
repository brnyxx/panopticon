# SENT-004 — Unsanitized tool content in prompt

## Problem
Tool-controlled text flows into a later model prompt without a configured trusted sanitizer. The static rule tracks values derived from tool output or tool descriptions and reports their use in OpenAI Responses or Chat Completions calls, or in the return value of a recognized prompt-building function.

## Impact
Untrusted tool content may influence instructions or messages supplied to a model. This can alter prompt context or cause the model to treat tool content as instructions; the actual effect depends on the reachable flow and model integration.

## Evidence
The AST rule `sentinel.sent004.unsanitized-tool-content` marks values derived from `.text`, `.description`, or `.content` attributes, and from `call_tool` or `list_tools` calls. It propagates those values through assignments, recognizes configured sanitizer names, and records a `prompt-taint` match when unsanitized data reaches `responses.create` or `chat.completions.create` through `input`, `instructions`, or `messages`, or reaches a recognized prompt function's return.

## Recommended action
Pass tool-controlled text through a configured trusted sanitizer before constructing or returning model prompt content. Keep the sanitizer configuration aligned with the implementation used by the scanned code.

## How to verify
Run `pano scan <path>` again. The SENT-004 finding should be absent when tool-derived text reaching each analyzed prompt sink has first passed through a configured sanitizer.

## Limits
This is static intraprocedural AST evidence, not an observation of model execution or proof that prompt injection occurred. The rule covers only recognized Python sources, assignments, sanitizer configuration, prompt sinks, and prompt functions; interprocedural flows, aliases it cannot resolve, other model APIs, dynamic values, and unscanned files may not be detected.
