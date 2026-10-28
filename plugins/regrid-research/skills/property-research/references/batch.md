# Shared budgets and requested checkpoints

## Contents

- [One allowance across stages](#one-allowance-across-stages)
- [Resume without duplicate retrieval](#resume-without-duplicate-retrieval)
- [Optional offline helper](#optional-offline-helper)

Use the envelope from [composition](composition.md) for a batch, handoff, or
checkpoint: legacy `1.0` remains supported; explicitly select `1.1` for tagged
search queries or reconciliation. The ledger accounts for this workflow's requests; account
usage counters can include other clients and cannot replace it.

## One allowance across stages

`budget` carries `max_requests`, `max_records`, `attempted_requests`,
`returned_records`, and `uncertain_records`. Limits are finite nonnegative
integers. A finite list defaults to one bounded one-result lookup per distinct
input; a supplied lower limit wins. Do not count reused evidence as a new lookup.
Count every API executor invocation against `max_requests`: parcel lookups,
count-only queries, usage/authentication diagnostics, and failed or uncertain
attempts. A non-billable diagnostic still consumes one request; a usage-only
diagnostic reserves zero parcel records. Local tool listing/schema inspection
and documentation-only discovery are not API executor calls and do not consume
API requests. Remote discovery still obeys offline/no-network instructions. Pass
the same remaining allowance and constraints to setup or other consumers.

For open-ended searches, use count-only queries when supported to estimate scope,
then paginate only within the remaining allowance. A list of addresses does not
authorize a broader owner search. Honor the endpoint's actual parameter schema;
count-only and pagination options are not universal.

Before dispatch, append a unique attempt with `attempt_id`, the affected
`input_ids`, `state: pending`, its bounded `record_limit`, and
`returned_records: null`. Increase attempted requests and reserve that record
limit. Dispatch only if both the request cap and the returned-plus-reserved
record cap permit it. Record reservations before calls; parallel stages must use
a single serialized coordinator, not independent copies of the allowance.

After a definite result, set state to `success` or `error`, record the actual
returned record count, and release its reservation. Retain all attempts, including
zero-result and failed calls. After a timeout or other unknown outcome, use
`uncertain` with null returned count and retain the full reservation. Never claim
zero consumption or automatically retry an uncertain request. Account usage may
lag and is not enough by itself to reconcile a specific attempt.

The counters must agree with the ledger:

- `attempted_requests` equals the number of attempts.
- `returned_records` sums known counts from resolved attempts and authoritative
  counts from version `1.1` reconciliation records.
- `uncertain_records` sums `record_limit` for pending/uncertain attempts without
  an accepted reconciliation.
- Remaining requests are `max_requests - attempted_requests`.
- Available records are `max_records - returned_records - uncertain_records`.

If the server returns more than the requested limit, preserve the actual count,
stop further retrieval, and report the overshoot; never clamp facts to make the
ledger appear compliant. New authorization may change limits, never consumption.
These are conservative workflow limits, not guaranteed billing caps.

In version `1.1`, reserve setup/usage diagnostics with
`reserve_attempt(..., input_ids=[], record_limit=0, kind="diagnostic")`; ordinary
lookup attempts use `kind="lookup"`. A diagnostic consumes a request without
pretending to evaluate a property row. Use `1.1` when diagnostics need to be
represented in a legacy workflow; upgrade it without replacing its history.

Reconcile an uncertain attempt only from an authoritative, per-attempt receipt
whose evidence the caller independently verifies. Use
`reconcile_attempt(document, attempt_id, proof, evidence_verified=True)` with
proof fields `provider`, `evidence_id`, `retrieved_at`, `attempt_id`,
`returned_records`, and nullable `source_url`. The proof must identify that exact
attempt; aggregate account usage is insufficient. The helper validates structure
and accounting but cannot authenticate the provider or receipt; never set the
verification flag merely because a document parses. Reconciliation appends a
record and preserves the original uncertain attempt and evidence. It replaces
the reservation with the proven count, preserves attempted-request consumption,
and does not retry the request or silently change input results. Preserve an
overshoot and stop if the proven count exceeds the allowance.

## Resume without duplicate retrieval

Persist a checkpoint only when the user requests saving/resuming or approves a
specific file destination. Do not write personal property data into the plugin
source, shared templates, or archives. Save the complete envelope atomically to
the chosen path; keep credentials and raw token-bearing requests out of it.

On resume, validate schema version, unique workflow/input/attempt IDs, original
inputs, status pairs, and counter arithmetic before making calls. Preserve input
order and the existing budget. A changed input must get a new ID or explicit
replacement instruction, not silently reuse another property's result.

Skip completed `success` rows, including ambiguous and unmatched rows, and reuse
their evidence for presentation. Skip `error` rows unless the user authorizes a
specific retry that fits the remaining budget. Pending attempts after interruption
are unresolved: treat them like uncertain outcomes and do not reissue their calls.
Proceed only with genuinely `not_attempted` inputs not covered by unresolved
attempts. A caller's explicit refresh/retry creates a new attempt and preserves
the old evidence and accounting. Resolve ambiguity only within authorized scope.

Report completed, ambiguous, unmatched, failed, and unattempted rows separately,
along with uncertain attempts and remaining allowance. Do not claim a batch has
completed merely because its first request and continuation plan were prepared.

## Optional offline helper

Run the packaged [workflow.py](../scripts/workflow.py) with Python 3.10+; it uses
only the standard library, so no package installation is required. It performs
no API calls or credential reads. Execute it for validation and persistence;
read its source only when integrating its functions into a batch runner.

After the user requests a checkpoint destination, prepare a complete envelope
using the result schema linked from `SKILL.md`; consult the synthetic example
only if needed. Use the helper's default `1.0` for legacy address/parcel requests,
or explicitly pass `schema_version="1.1"` to `new_workflow` for tagged queries.
Use `upgrade_workflow` to migrate an existing `1.0` envelope without resetting
rows, evidence, attempts, or consumed budget; do not simply rewrite its version.
Validate it, fix reported field/invariant errors, and repeat validation until it
passes. Save to the requested destination, then validate the saved file before
resuming. The `save` command also validates before writing atomically:


```sh
python3 /path/to/property-research/scripts/workflow.py validate /path/to/result.json
python3 /path/to/property-research/scripts/workflow.py save /path/to/result.json /path/to/checkpoint.json
python3 /path/to/property-research/scripts/workflow.py validate /path/to/checkpoint.json
python3 /path/to/property-research/scripts/workflow.py pending /path/to/checkpoint.json
```

Substitute the actual installed skill directory and user-requested file paths.
Use `save ... --replace` only for an explicitly requested checkpoint update; the
default refuses an existing destination. Do not copy the synthetic example as
real property evidence. If validation fails, correct the envelope and rerun; do
not dispatch resumed calls from invalid state.

For a controlled batch runner, import its functions: `new_workflow`,
`reserve_attempt`, `complete_attempt`, `set_result`, `reuse_result`,
`pending_input_ids`, `save_checkpoint`, and `load_checkpoint`. Functions return
new documents; they do not mutate the caller's ledger. Save a pending reservation
before dispatch when checkpointing is requested, then save the resolved state
after recording the response. `save_checkpoint` requires `requested=True` and
does not overwrite an existing path unless `replace=True` is explicitly supplied.
The helper does not decide address matches, verify source truth, run other skills,
or authorize requests. Keep those decisions in the research workflow.

If Python execution is unavailable, the skill can still produce a contract-shaped
handoff and maintain the ledger in the task. Do not claim the helper ran or a
checkpoint was saved. Validate before using such a handoff for resumed requests.
