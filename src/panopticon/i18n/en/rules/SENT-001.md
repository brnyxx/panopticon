# SENT-001 — Overly broad tool permission scope

## Problem
The tool declares filesystem or network access broader than the access used by its handler. The analyzer reports a finding when a tool is missing from the permissions manifest or when declared scopes differ from statically detected usage.

## Impact
When a declaration grants resources beyond those required by the handler, the declared capability boundary is wider than the code path examined by the analyzer. Dynamic paths or hosts prevent an exact comparison and are treated as broader.

## Evidence
The AST analyzer reads `sentinel.permissions.yaml` and scans Python MCP tool regions. It records literal filesystem read/write paths and network hosts from recognized calls, then compares them with the tool's declared `filesystem.read`, `filesystem.write`, and `network` scopes. Evidence points to the relevant call or tool region.

## Recommended action
Narrow each declared scope to the resources the handler actually requires. A broad scope with a `broad_scope_justification` is exempt from this finding.

## How to verify
Run `pano scan <path>` again with the permissions manifest present. The SENT-001 finding should be absent when every tool is declared and its declared scopes match the statically detected scopes (or have a broad-scope justification).

## Limits
This is static AST evidence, not an observation of execution. Only recognized Python calls and literal values are compared; aliases, dynamic values, unscanned files, and behavior outside the analyzed handler may not be represented.
