# Match decisions and answers

## Contents

- [Match decisions](#match-decisions)
- [Answer format](#answer-format)

## Match decisions

Compare situs/property fields, not the owner's mailing address. Normalize case,
punctuation, conventional street suffixes, and ZIP+4 to ZIP5. Preserve house
numbers, directional words, and unit identifiers. A score or `limit=1` result
does not establish uniqueness or an exact match.

| Status | Evidence | Action |
| --- | --- | --- |
| Confirmed | Supplied house number, street, locality/ZIP, and unit agree; or the requested scoped APN/parcel ID agrees. No conflicting identity evidence. | Report the returned record's facts. |
| Ambiguous | A necessary identity field is missing, a unit is unresolved, or several plausible parcels/units remain. | Explain the uncertainty and request the smallest useful clarification. Do not assign an owner to the requested property yet. |
| Unmatched | Successful empty results, or every candidate conflicts with the requested identity, such as a different house number. | Say no matching parcel was found in this lookup. A rejected nearby candidate is not an ownership answer. |
| Not assessed | Lookup failed or no evidence has been evaluated. | Preserve `error` or `not_attempted` execution status; do not convert it into “no results.” |

For a requested unit, a building-level parcel with no unit evidence is ambiguous.
When multiple parcels share an address, retain separate IDs and owners; do not
merge them or imply that the first record represents all of them. Confirm an
individual parcel only when the supplied identifier distinguishes it. Missing
owner data does not change a confirmed address into an unmatched address.

## Answer format

Honor the caller's requested prose, table, JSON, or report structure; a calling
skill's narrower budget and output format take precedence over defaults. Keep
uncertainty and provenance regardless of presentation. Do not impose a prose
opening on a JSON handoff. For a direct prose answer with a confirmed match and
a nonblank owner field, a useful default is: “Regrid lists
**[recorded owner]** as the owner of **[matched address]**.” For a confirmed match
without that field, say the parcel matched but its response has no recorded owner
value. For other statuses, lead with the uncertainty, no-match result, or error.

Include parcel ID and source refresh date when available; if absent, identify
them as unavailable when relevant. Retrieval time is not source freshness.
Include sale date, sale price, or mailing address only when relevant. For batches,
use one row per input with match status, matched address, owner, parcel ID, and
refresh date; retain ambiguity/error notes. Avoid full JSON or geometry dumps.

Distinguish recorded ownership from beneficial ownership: an LLC name does not
identify its members. Assessed value is not market value; a sale date is not a
source refresh date. Missing fields are unknown, not zero. Describe unverified
address matches explicitly. Link to source records only when a real usable URL
is supplied; do not invent one or expose an authenticated request URL.
