# SENT-011 — Malformed schema input processed

## Problem
The server processed a required tool argument that was missing or had the wrong type, rather than rejecting the request before handler execution. This dynamic rule concerns required-field and declared-type processing at the tool boundary.

## Impact
Malformed input can reach handler logic and produce unexpected results, errors, or side effects. The practical impact depends on the argument, handler, and downstream operations; this rule is cataloged with Low impact.

## Evidence
The pinned dynamic catalog defines `SENT-011` as “Malformed schema input processed” and describes it as processing a missing or wrong-type required tool argument. The pinned prober builds baseline values for declared required properties, then performs a bounded inert probe by either omitting a required field (`__SENTINEL_OMIT__`) or replacing a selected property with an object carrying `__sentinel_wrong_type__` (redacted evidence marker: `__SENTINEL_WRONG_TYPE__`). A non-error response records that this probe input was processed; it does not by itself establish a security verdict or downstream effect.

## Recommended action
Validate required fields and their declared types before invoking the handler. Reject missing or mismatched arguments with a structured protocol error, including nested argument envelopes, and keep runtime validation aligned with the published input schema.

## How to verify
Run the bounded dynamic probe through `pano scan <path>` in a mode that includes runtime probing. Repeat the SENT-011 omission and wrong-type cases for each applicable required field and confirm that validation rejects them before handler execution, while preserving ordinary valid calls.

## Limits
This evidence covers only the selected tool, schema properties, and probe cases reached during the run. The prober uses inert markers and bounded requests; it does not exercise every malformed shape, optional field, alias, dynamic dispatch path, or downstream side effect. Missing or non-object schemas, unselected tools, transport failures, and unscanned files may remain outside coverage. A probe response alone is not proof of exploitability, and an error alone does not prove that all malformed inputs are rejected.
