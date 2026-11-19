# Premium datasets (US parcels)

This skill applies this guidance to US parcels only. Premium datasets are off by
default. Where the endpoint's live schema supports a flag, send it as `false`
unless the user has authorized that dataset in this task. Premium flags may cost
extra against the user's Regrid plan. Authorization for one dataset does not cover
another, and it does not cover a broader search or extra candidates.

Before sending a premium flag, confirm the selected endpoint supports it in the
live schema. In the result row's `notes` field (an array of prose strings), record
each premium flag actually sent with its value (for example "return_zoning=true,
authorized by the user"), and state that the other premium flags were sent as
`false`.

## return_zoning

- Answers: zoning fields for the matched parcel, when the user asks about zoning.
- Authorization: needs the user's authorization and may cost extra. Without it,
  send `return_zoning=false`.
- Handoff: add a `notes` entry with the value sent and the authorization basis.

## return_enhanced_ownership

- Answers: additional ownership fields beyond the recorded owner on the parcel.
- Authorization: needs the user's authorization and may cost extra. Without it,
  send `return_enhanced_ownership=false`.
- Handoff: add a `notes` entry with the value sent and the authorization basis.
- A recorded owner is not the beneficial owner. Do not infer members, officers,
  or controlling people from an LLC or trust name, a mailing address, or enhanced
  ownership fields unless the dataset itself says so.

## return_matched_buildings

- Answers: building records matched to the parcel or query, when the user asks
  for building-level matches.
- Authorization: needs the user's authorization and may cost extra. Without it,
  send `return_matched_buildings=false`.
- Handoff: add a `notes` entry with the value sent and the authorization basis.
  Keep each building match tied to its parcel ID.

## return_matched_addresses

- Answers: address records matched to the parcel or query, when the user asks
  for matched addresses.
- Authorization: needs the user's authorization and may cost extra. Without it,
  send `return_matched_addresses=false`.
- Handoff: add a `notes` entry with the value sent and the authorization basis.
  Under this skill's match rules in SKILL.md, matched addresses are not by
  themselves evidence that the requested property is confirmed.
