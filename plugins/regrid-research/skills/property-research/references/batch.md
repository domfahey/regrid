# Shared budgets and requested checkpoints

## Contents

- [Default budgets](#default-budgets)
- [One allowance across stages](#one-allowance-across-stages)
- [CLI and suggestion requests](#cli-and-suggestion-requests)
- [Neighbour requests](#neighbour-requests)
- [Resume without duplicate retrieval](#resume-without-duplicate-retrieval)
- [Optional offline helper](#optional-offline-helper)

Use the [result schema](result.schema.json) envelope for batches, handoffs, or
checkpoints (see [composition](composition.md) for fields): `1.0` remains supported;
select `1.1` for tagged search queries or reconciliation. The ledger tracks this
workflow's requests conservatively and is not a billing cap; account usage counters
reflect other clients and lag, so they cannot replace it.

## Default budgets

A finite list authorizes one bounded one-result lookup per distinct input by default
(keep duplicate output rows). Honor lower caller limits and proceed within authorized
scope without renewed permission. Open-ended searches require geography and a finite
total record budget first. Broader searches, extra candidates beyond budget, and
unrequested premium datasets need additional authorization; ambiguity resolution within
an explicit candidate budget does not. Page only within the agreed budget and one task.

Share one attempt ledger across stages: reserve possible records before dispatch, keep
reservations on unknown outcomes, never reset consumption, and never auto-retry a
potentially billable uncertain call. Stop at budget, auth/permission failure, or
exhaustion. Report partial counts, per-input statuses, unfinished input IDs, and when
continuing needs new authorization.

## One allowance across stages

`budget` holds finite nonnegative integers: `max_requests`, `max_records`,
`attempted_requests`, `returned_records`, and `uncertain_records`. Reused evidence
never consumes a lookup. Count every API executor call against `max_requests` (parcel
lookups, `return_count` queries, diagnostics, and failed/uncertain calls; diagnostics
reserve zero records). Local tool/schema/doc inspection consumes no API requests but
still obeys offline constraints. Pass remaining allowance and constraints to setup or
other consumers.

For open-ended searches, an optional `return_count` call (one request, zero records)
sizes results when supported; paginate only within remaining allowance. An address list
does not authorize an owner search; honor each endpoint's schema (`return_count` and
pagination are not universal).

Before dispatch, append a unique attempt (`attempt_id`, `input_ids`, `state: pending`,
bounded `record_limit`, `returned_records: null`), increment `attempted_requests`, and
reserve `record_limit`. Dispatch only when request and returned-plus-reserved record
caps allow it; parallel stages must share one serialized coordinator.

On a definite result, set `state` to `success` or `error`, record actual returned
records, and release the reservation (retain all attempts, including zero-result and
failed calls). On timeout or unknown outcome, set `uncertain` with `null` returned
count and keep the full reservation.

Ledger invariants:

- `attempted_requests` equals the number of attempts.
- `returned_records` sums known counts from resolved attempts and proven counts from
  `1.1` reconciliation records.
- `uncertain_records` sums `record_limit` for pending/uncertain attempts lacking
  accepted reconciliation.
- Remaining requests: `max_requests - attempted_requests`.
- Available records: `max_records - returned_records - uncertain_records`.

If the server returns more than `record_limit`, record the actual count, stop further
retrieval, and report the overshoot; never clamp facts. New authorization may adjust
limits, never consumption.

In `1.1`, reserve diagnostics with
`reserve_attempt(..., input_ids=[], record_limit=0, kind="diagnostic")` and lookups with
`kind="lookup"`. Upgrade legacy `1.0` workflows via `upgrade_workflow` rather than
replacing history.

Reconcile an uncertain attempt only from an authoritative, independently verified
per-attempt receipt using
`reconcile_attempt(document, attempt_id, proof, evidence_verified=True)` with
`provider`, `evidence_id`, `retrieved_at`, `attempt_id`, `returned_records`, and
nullable `source_url`. Aggregate usage is insufficient, and parsing alone never
justifies `evidence_verified=True`. Reconciliation appends a record while keeping the
original uncertain attempt, replaces the reservation with the proven count, preserves
request consumption, and never retries or alters input results; stop on overshoot.

## CLI and suggestion requests

Every request needs a reserved attempt, including CLI and suggestion calls. The CLI is
ledger-unaware: reserve before each command that can make a request, then complete from
the last stderr line starting `regrid: requests made: N` (`address-map` and `freshness`
print it before their error line, so match the prefix, not the position); an unreadable
line leaves the attempt uncertain and is never retried. A cache hit reports 0.

- No-record calls (`regrid freshness`, typeahead over CLI or MCP, schema, usage, tiles):
  `reserve_attempt(doc, [], 0, kind="diagnostic")`, then complete with the actual
  outcome: `complete_attempt(doc, attempt_id, "success", 0)` or `"error"` with 0 when
  it failed, or record an unknown outcome with `complete_attempt(doc, attempt_id, "uncertain")`.
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

Skip `complete_attempt` for an already `uncertain` attempt (it accepts only `pending`).
Without a verified receipt, stop and keep the reservation; never transition a
still-running call or infer zero consumption from a crash. These calls neither retry
nor save files.

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

Run `<skill>/scripts/workflow.py` with Python 3.10+ (stdlib only, no API calls or
credential reads) for validation and persistence; read its source only when integrating
into a batch runner.

For a requested checkpoint destination, build the envelope from the result schema
linked in `SKILL.md` (default `1.0`, or `schema_version="1.1"` in `new_workflow`;
migrate `1.0` with `upgrade_workflow` without altering history). Validate, fix errors,
and save atomically (`save` validates first); validate again before resuming:

```sh
python3 "<skill>/scripts/workflow.py" validate /path/to/result.json
python3 "<skill>/scripts/workflow.py" save /path/to/result.json /path/to/checkpoint.json
python3 "<skill>/scripts/workflow.py" validate /path/to/checkpoint.json
python3 "<skill>/scripts/workflow.py" pending /path/to/checkpoint.json
```

Substitute the installed skill directory and requested file paths. Use
`save ... --replace` only for an explicit checkpoint update; never copy the synthetic
example as real evidence, and never dispatch resumed calls from invalid state.

For a controlled batch runner, import its functions: `new_workflow`, `validate`,
`upgrade_workflow`, `reserve_attempt`, `complete_attempt`, `reconcile_attempt`,
`set_result`, `reuse_result`, `pending_input_ids`, `tighten_budget`,
`save_checkpoint`, and `load_checkpoint`. Functions return
new documents; they do not mutate the caller's ledger. Save a pending reservation
before dispatch when checkpointing is requested, then save the resolved state
after recording the response. `save_checkpoint` requires `requested=True` and
does not overwrite an existing path unless `replace=True` is explicitly supplied.
The helper does not decide address matches, verify source truth, run other skills,
or authorize requests. Keep those decisions in the research workflow.

If Python execution is unavailable, the skill can still produce a contract-shaped
handoff and maintain the ledger in the task. Do not claim the helper ran or a
checkpoint was saved. Validate before using such a handoff for resumed requests.
