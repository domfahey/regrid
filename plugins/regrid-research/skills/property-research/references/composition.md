# Reusable research results

Use [result.schema.json](result.schema.json) version `1.0` for structured handoffs
and requested checkpoints. [result-example.json](result-example.json) is synthetic.
Prose answers need not expose JSON, but preserve the same distinctions. This is
a portable contract, not a requirement to install another skill or write a file.

## Envelope and identity

The envelope contains `schema_version`, `workflow_id`, `results`, `budget`, and
`attempts`. One workflow ID and shared ledger follow the work through all stages.
Each result retains its unique `input_id` and original `requested` address,
parcel ID, and geographic scope. Use caller IDs unchanged, or assign stable row
IDs once. Keep duplicate input rows even when one retrieval serves both.

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
no API budget. Missing optional skills do not block a plain answer or portable
result. Never claim a downstream action happened merely because a handoff exists.

## Validation and compatibility

Before handoff or resume, validate structural fields against the schema and ledger
arithmetic using the workflow helper when available. Fix reported fields, rerun
validation, and repeat until it passes before saving or making resumed requests.
Then review match evidence and provenance separately; passing structure is not
proof of source truth. Unknown schema versions must not be silently
coerced. Duplicate IDs, invalid status pairs, invented provenance, and budget
resets invalidate a handoff. The schema cannot prove source truth or address
identity; the research rules still apply. Consumers may present fewer fields,
but must not discard the original evidence needed by later stages.
