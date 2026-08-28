# SENT-003 — Missing tool input validation

## Problem
A Python MCP tool handler consumes an untyped or broadly typed parameter before framework or explicit validation. The static rule flags keyword arguments, unannotated parameters, parameters annotated as `Any` or `dict`, and dispatcher `arguments` or `kwargs` uses when no recognized validation occurs first.

## Impact
Without a recognized validation step before first use, the handler may process tool input whose declared shape or types have not been checked on the analyzed path. The practical impact depends on how that value is used at runtime.

## Evidence
The AST rule `sentinel.sent003.missing-input-validation` examines Python MCP tool regions. It treats concrete annotations as typed, recognizes `model_validate`, `parse_obj`, `validate`, and `jsonschema.validate` calls as validation, and records the first unvalidated parameter or dispatcher-argument use. A finding identifies the matched parameter or use location.

## Recommended action
Use concrete handler types, Pydantic models, or JSON Schema validation before first use of each tool parameter. Validate dispatcher arguments before indexing or reading them.

## How to verify
Run `pano scan <path>` again. The SENT-003 finding should be absent when every analyzed tool parameter is concretely typed or has a recognized validation call before its first use, and dispatcher arguments are validated before access.

## Limits
This is static AST evidence, not an observation of a tool call or proof that malformed input was accepted. Only the configured Python MCP patterns and recognized validation calls are covered; aliases, custom validators, implicit framework behavior, dynamic dispatch, unscanned files, and uses outside the analyzed region may not be represented.
