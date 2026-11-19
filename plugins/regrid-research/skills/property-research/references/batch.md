# Shared budgets and requested checkpoints

## Contents

- [Default budgets](#default-budgets)
- [One allowance across stages](#one-allowance-across-stages)
- [CLI and suggestion requests](#cli-and-suggestion-requests)
- [Neighbour requests](#neighbour-requests)
- [Resume without duplicate retrieval](#resume-without-duplicate-retrieval)
- [Optional offline helper](#optional-offline-helper)

Use the envelope from the [result schema](result.schema.json) for a batch, handoff, or
checkpoint (see also [composition](composition.md) for its fields): legacy `1.0` remains supported; explicitly select `1.1` for tagged
search queries or reconciliation. The ledger accounts for this workflow's requests; account
usage counters can include other clients and cannot replace it.

## Default budgets

A finite list authorizes one bounded one-result lookup per distinct input by
default; retain duplicate output rows. Honor lower caller limits and proceed
within authorized scope without renewed permission. For open-ended searches,
establish geography and a finite total record budget first. Broader searches,
extra candidates beyond the budget, and unrequested premium datasets require
additional authorization; ambiguity resolution within an explicit candidate
budget does not. Page only within the agreed budget and one task.

Carry one shared attempt ledger across stages, reserve possible records before
dispatch, and retain reservations for unknown outcomes. Never reset consumption or
automatically retry a potentially billable uncertain request. Stop at budget,
auth/permission failure, or exhaustion; these workflow limits are not billing caps.
Report partial counts and per-input statuses, identify unfinished input IDs, and
explain when continuing requires authorization beyond the cap. Never omit them.
The rules below say what counts and how to record it.

## One allowance across stages

`budget` carries `max_requests`, `max_records`, `attempted_requests`,
`returned_records`, and `uncertain_records`. Limits are finite nonnegative
integers. Do not count reused evidence as a new lookup.
Count every API executor invocation against `max_requests`: parcel lookups,
count-only queries, usage/authentication diagnostics, and failed or uncertain
attempts. A non-billable diagnostic still consumes one request; a usage-only
diagnostic reserves zero parcel records. Local tool listing/schema inspection
and documentation-only discovery are not API executor calls and do not consume
API requests. Remote discovery still obeys offline/no-network instructions. Pass
the same remaining allowance and constraints to setup or other consumers.

For open-ended searches, an optional `return_count` call (one request, zero records)
sizes the search when supported; then paginate only within the remaining
allowance. A list of addresses does not authorize a broader owner search. Honor the endpoint's actual parameter schema;
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

## CLI and suggestion requests

Every request needs a reserved attempt, including CLI and suggestion calls. The CLI is
ledger-unaware: reserve before each command that can make a request, then complete from
the last stderr line starting `regrid: requests made: N` (`address-map` and `freshness`
print it before their error line, so match the prefix, not the position); an unreadable
line leaves the attempt uncertain and is never retried. A cache hit reports 0.

- No-record calls (`regrid freshness`, typeahead over CLI or MCP, schema, usage, tiles):
  `reserve_attempt(doc, [], 0, kind="diagnostic")`, then complete with the actual
  outcome: `complete_attempt(doc, attempt_id, "success", 0)` or `"error"` with 0 when
  it failed, or leave it uncertain when the count or outcome is unknown.
- `/parcels/path`: `kind="lookup"` for the input, record_limit 1. When the input is already
  resolved (a refresh, or a path lookup after typeahead), reserve with
  `authorized_retry=True`; the user's refresh request is the authorization.
- Record lookups: reserve with the input ID and `record_limit` equal to the page limit.
- Neighbours: see [neighbour requests](#neighbour-requests).

Paged searches: each page is one attempt with `record_limit` equal to that page's
requested limit (three pages, three attempts; the CLI prints `regrid: up to K requests for N records`,
so reserve K attempts). The first page reserves normally; every later page reuses the same
input ID, so reserve it with `authorized_retry=True`. Each page requests at most the
remaining count, so the workflow needs K = ceil(N / limit) requests and N records
remaining. If it cannot cover that, refuse to page and report the shortfall. Paging
positions are not saved in checkpoints; a resumed open-ended search needs fresh
authorization before it pages again.

## Neighbour requests

Neighbouring parcels are one `kind="lookup"` request with `authorized_retry=True`, the
subject's input ID, and record_limit 25. If the user already asked for neighbours,
state the cost ("one request, up to 25 records") and proceed if the budget check
below passes; otherwise offer it with that cost and wait. A single-property map with
no workflow ledger needs no entry. When a workflow ledger or handoff is in use,
the user's neighbours request is the authorization. Check that at least one request
and 25 records remain, then reserve. Complete it with the actual returned count; an
unknown outcome stays uncertain. If the remaining budget is short, do not call: report
that neighbours exceed the workflow budget. The request itself is described in the
[map guide](map.md#neighbouring-parcels) (see also).

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
are unresolved: retain their reservations and do not reissue their calls.
Once the interrupted dispatcher is no longer active and its outcome cannot be
recovered, explicitly mark that pending attempt uncertain before reconciliation:

```python
# workflow is the imported packaged helper; document is a validated checkpoint.
document = workflow.complete_attempt(document, attempt_id, "uncertain")
# This transition preserves the reservation and attempted-request count.
document = workflow.upgrade_workflow(document)  # Explicitly enables 1.1 if needed.
# Only after independently verifying an authoritative receipt for this attempt:
document = workflow.reconcile_attempt(document, attempt_id, proof, evidence_verified=True)
```

For an attempt already marked `uncertain`, skip `complete_attempt`; it accepts
only pending attempts. Without a verified receipt, stop after recording uncertainty
and retain the reservation. Do not transition a still-running request or infer
zero consumption from a crash. These helper calls neither retry nor save a file.

An explicit refresh of a saved result uses `/parcels/path` with the saved `path`:
one request, one record, reserved with `authorized_retry=True` because the input is resolved. If the saved result has no `path`, stop and ask;
never fall back to an unscoped search.

Proceed only with genuinely `not_attempted` inputs not covered by unresolved
attempts. A caller's explicit refresh/retry creates a new attempt and preserves
the old evidence and accounting. Resolve ambiguity only within authorized scope.

Report completed, ambiguous, unmatched, failed, and unattempted rows separately,
along with uncertain attempts and remaining allowance. Do not claim a batch has
completed merely because its first request and continuation plan were prepared.

## Optional offline helper

Run the packaged `<skill>/scripts/workflow.py` with Python 3.10+; it uses
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
python3 "<skill>/scripts/workflow.py" validate /path/to/result.json
python3 "<skill>/scripts/workflow.py" save /path/to/result.json /path/to/checkpoint.json
python3 "<skill>/scripts/workflow.py" validate /path/to/checkpoint.json
python3 "<skill>/scripts/workflow.py" pending /path/to/checkpoint.json
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
