# Premium datasets (US parcels)

Premium datasets are US-only and off by default. Send each flag as `false` unless
the user has authorized that dataset in this task. Premium flags may cost extra
against the user's Regrid plan. Authorization for one dataset does not cover
another, and it does not cover a broader search or extra candidates.

Before sending a premium flag, confirm the selected endpoint supports it in the
live schema. Record every premium flag actually sent in the handoff request record
with its value (for example `return_zoning=true`), and record unrequested flags
as `false`.

## return_zoning

- Answers: zoning fields for the matched parcel, when the user asks about zoning.
- Authorization: needs the user's authorization and may cost extra. Without it,
  send `return_zoning=false`.
- Handoff: record `return_zoning` with the value sent and note that the user
  authorized zoning data.

## return_enhanced_ownership

- Answers: additional ownership fields beyond the recorded owner on the parcel.
- Authorization: needs the user's authorization and may cost extra. Without it,
  send `return_enhanced_ownership=false`.
- Handoff: record `return_enhanced_ownership` with the value sent and note the
  authorization.
- A recorded owner is not the beneficial owner. Do not infer members, officers,
  or controlling people from an LLC or trust name, a mailing address, or enhanced
  ownership fields unless the dataset itself says so.

## return_matched_buildings

- Answers: building records matched to the parcel or query, when the user asks
  for building-level matches.
- Authorization: needs the user's authorization and may cost extra. Without it,
  send `return_matched_buildings=false`.
- Handoff: record `return_matched_buildings` with the value sent and note the
  authorization. Keep each building match tied to its parcel ID.

## return_matched_addresses

- Answers: address records matched to the parcel or query, when the user asks
  for matched addresses.
- Authorization: needs the user's authorization and may cost extra. Without it,
  send `return_matched_addresses=false`.
- Handoff: record `return_matched_addresses` with the value sent and note the
  authorization. Matched addresses do not change the match status of the
  requested property.
