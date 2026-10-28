# Reusable research results

For prose from supplied evidence, this guide is sufficient: evaluate identity,
uncertainty, conflicts, and provenance without loading the schema or example and
without making a request. Load [result.schema.json](result.schema.json) only for
a structured handoff, requested checkpoint, or contract validation. The
[synthetic example](result-example.json) is optional when an example is needed.
The contract is portable; it does not require another skill or a saved file.
Legacy version `1.0` remains supported; explicitly use version `1.1` for tagged
owner, point, area, or filter queries and reconciliation records.

## Envelope and identity

The envelope contains `schema_version`, `workflow_id`, `results`, `budget`, and
`attempts`. One workflow ID and shared ledger follow the work through all stages.
Each result retains its unique `input_id` and original `requested` address,
parcel ID, and geographic scope. Use caller IDs unchanged, or assign stable row
IDs once. Keep duplicate input rows even when one retrieval serves both.

Version `1.1` can describe searches directly in `requested` instead of inventing
an address: `query_type: owner` uses `owner` and `scope`; `point` uses `lat`, `lon`,
and positive `radius` in meters; `area` uses `bbox` as west/south/east/north;
`filter` uses `scope` and a nonempty `filters` mapping of field → operator →
JSON value. Preserve nested values; the live endpoint schema, not the handoff
contract, determines supported operators.
Use the schema for exact bounds. Legacy address/parcel requests remain accepted.
For a search, evaluate whether each returned parcel satisfies its actual query;
do not imply that a multi-parcel owner or area search identifies one property.

`lookup_status` describes the evidence operation: `success`, `error`, or
`not_attempted`. `match_status` describes property identity: `confirmed`,
`ambiguous`, `unmatched`, or `not_assessed`. Errors and unattempted inputs are not
assessed; only successful evidence evaluation yields the first three match
statuses. Processing supplied evidence can succeed without making a new call.
An unmatched successful result may retain rejected candidates with explanatory
notes; never present those candidates as the requested property's owners.

Each candidate is a separate observation with parcel ID, matched address, `facts`,
and `provenance`. Facts can contain `recorded_owner`, `sale_price`, `sale_date`,
`assessed_value`, and other requested attributes. Preserve explicit nulls; omit
absent facts and list relevant unavailable requested fields in `missing_fields`.
Neither omission nor null means zero. Unknown provenance fields are null.

Provenance names the provider, evidence ID, original retrieval timestamp, source
refresh date, and a real source URL when supplied. Do not invent URLs or expose
authenticated URLs. Use ISO timestamps when known; do not replace source dates
with the current time. Evidence IDs distinguish observations within the workflow.
On failure, retain a sanitized error category/message and whether the request's
outcome is uncertain. Do not attach tokens, headers, or raw credential-bearing
exception strings.

## Supplied evidence and conflicts

Accept existing records or contract envelopes as input. Check they refer to the
requested property and contain enough evidence for the requested facts. Record
missing provenance as unknown and disclose that limitation when material; do not
upgrade supplied text into a verified API response. Retrieve only missing evidence,
an explicit refresh, or a necessary correction within the remaining budget.

When two observations conflict, keep both candidates with their own evidence IDs,
dates, providers, and facts. Do not overwrite an older result or combine fields
into a fictitious single response. A conflict about identity makes the match
ambiguous. Conflicting owners for the same confirmed parcel can retain a confirmed
identity, but the ownership answer must describe the conflict rather than assert
a single owner. A newer retrieval timestamp alone does not establish newer source
data. Explain any evidence-based selection instead of silently resolving it.

## Handoff rules

| Consumer | Preserve or constrain |
| --- | --- |
| Report | Preserve match uncertainty, missing facts, provider, and source freshness. Format existing evidence without another lookup unless refresh was requested. |
| Spreadsheet | Keep stable input IDs and all rows, including unmatched/error/unattempted rows. Multiple candidates may use child rows keyed to input ID; never collapse their owners. Keep null/unknown distinct from zero. |
| CRM | Produce proposed field changes with supporting evidence. Research permission does not authorize external writes; use the user's separate write authorization. |
| Entity research | Treat the recorded LLC as an investigation lead. Keep corporate/member evidence separate with its own sources; do not attribute it to Regrid's parcel record. |

A consumer inherits the same workflow budget; it does not receive a new allowance.
A narrower caller limit wins. If a new limit is below consumption, stop retrieval
and report the over-limit state without rewriting history. Formatting itself uses
no API budget. Offline/no-network instructions pass to every stage, including
setup: they prohibit remote docs/schema discovery and API diagnostics as well as
parcel retrieval. API diagnostics use the same finite request allowance; no
consumer or setup invocation creates a hidden allowance. Missing optional skills do not block a plain answer or portable
result. Never claim a downstream action happened merely because a handoff exists.

## Validation and compatibility

Before handoff or resume, validate structural fields against the schema and ledger
arithmetic using the workflow helper when available. Fix reported fields, rerun
validation, and repeat until it passes before saving or making resumed requests.
For supplied-evidence prose, review these distinctions directly; no structural
validation or JSON conversion is required. Then review match evidence and provenance separately; passing structure is not
proof of source truth. Unknown schema versions must not be silently
coerced. Duplicate IDs, invalid status pairs, invented provenance, and budget
resets invalidate a handoff. The schema cannot prove source truth or address
identity; the research rules still apply. Consumers may present fewer fields,
but must not discard the original evidence needed by later stages.

Version `1.1` adds `reconciliations` and explicit lookup/diagnostic attempt kinds.
Upgrade legacy envelopes through `upgrade_workflow`, which preserves evidence
and consumption and tags existing attempts as lookups. Reconciliation needs an
independently verified authoritative receipt tied to one attempt; see
[batch and resume](batch.md). An aggregate usage counter or structurally valid
proof cannot establish that receipt's authenticity. Append the proof without
rewriting the uncertain attempt; reconciliation never creates a retry allowance.
