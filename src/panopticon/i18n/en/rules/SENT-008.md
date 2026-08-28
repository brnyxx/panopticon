# SENT-008 — Out-of-scope tool execution

## Problem
The server executes a tool that is omitted from its declared permissions manifest. SENT-008 is the bounded runtime probe for whether an ungranted tool call is rejected at the capability boundary.

## Impact
Executing an ungranted tool can bypass the intended capability policy and expose operations that the manifest did not authorize. The probe result describes one isolated call; it does not establish the scope or consequence of any other execution.

## Evidence
The pinned dynamic catalog defines SENT-008 as “Out-of-scope tool execution”: the server executed a tool omitted from its declared permissions manifest. The prober loads the required permissions manifest, lists tools in a fresh session, and selects the first tool (sorted by name) that is not present in `manifest.tools`; when none is listed, it calls the fallback name `__sentinel_out_of_scope__`. A non-error response (`isError` false) records SENT-008 evidence. The request, bounded response, and sanitized logs are retained as dynamic evidence.

## Recommended action
Reject tool calls that are not granted by the active capability policy before invoking a handler. Apply the same manifest check to every transport and dispatch path, and return a protocol-level error for an ungranted name.

## How to verify
Run the dynamic scan in its isolated Docker probe environment. SENT-008 evidence should not be emitted when the selected ungranted name (or fallback name) is rejected with an error before handler execution. Confirm that ordinary calls for manifest-granted tools still work.

## Limits
This is bounded runtime evidence, not a guarantee for every unlisted name, transport, session, deployment, or dispatch path. The campaign performs the approved probe once in a fresh session and only tests the first lexicographically ungranted listed tool, or the fallback when no such tool is listed. It does not prove handler side effects, test every manifest state, or cover unlisted tools that are not advertised, alternate aliases, concurrent calls, transport failures, or unscanned code. A successful or failed probe alone does not establish an overall service-safety verdict.
