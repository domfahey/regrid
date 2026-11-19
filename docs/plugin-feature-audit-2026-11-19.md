# Regrid Research plugin: MCP and CLI feature audit

Date: 2026-11-19. Plugin version: 0.6.0. Scope: US parcels only.

This audit compares the plugin (`plugins/regrid-research`, skills `property-research` and
`setup`) with the Regrid MCP server's tools and with this repo's SDK/CLI
(`docs/api-coverage.md`, `regrid --help`).

**Verified on 2026-11-19:** the MCP server's US spec ("Regrid OpenAPI Specification
(reference)") exposes `/verse`, `/parcels/typeahead`, `/parcels/path`, and all
`/schemas/*` endpoints. This was checked with unauthenticated `list-endpoints` and
`get-endpoint` calls, which are documentation calls and use no API requests. The same
list also shows `/usage/detailed`, POST variants of `/parcels/point` and `/parcels/area`,
and the out-of-scope `/report`, `/client_token/typeahead` and `/ca/*` routes.

## MCP tools: complete

All seven tools (`list-specs`, `list-endpoints`, `search-endpoints`, `get-endpoint`,
`search`, `fetch`, `execute-request`) are documented in `references/mcp-tools.md`, with
each tool's role and whether it counts against the request budget. Only
`execute-request` makes API calls.

## Endpoint coverage

The skill uses:

| Endpoint | Purpose |
| --- | --- |
| `/parcels/address` | Address lookup |
| `/parcels/apn` | APN lookup (county scope) |
| `/parcels/owner` | Owner-name search |
| `/parcels/point` | Point or radius search |
| `/parcels/area` | Area (GeoJSON) search |
| `/parcels/query` | Field-filter search |
| `/parcels/{ll_uuid}` | Regrid ID lookup |
| `/usage` | Setup authentication check |

US read-only endpoints available in both the MCP server and the CLI that the skill does not use:

| Endpoint | CLI | Live parameters | What it would add |
| --- | --- | --- | --- |
| `/verse` | `regrid verse` | `return_geometry` | When Regrid last did a full data pull for each US and Puerto Rico county. |
| `/parcels/typeahead` | `regrid typeahead` | `query` (required) | Address lookup and validation, returning a parcel identifier (path) for each match. |
| `/parcels/path` | `regrid parcel-path` | `path` (required); the `return_*` flags for custom, field labels, stacked, zoning, matched buildings, matched addresses, enhanced ownership and parcels | One parcel by its Regrid path, optionally with premium datasets. |
| `/schemas/parcel`, `building`, `address`, `enhanced_ownership`, `zoning` | `regrid schema <name>` | `premium_only` (parcel only) | Field definitions, such as what `usedesc`, the zoning codes or the building fields mean. |

Notes from the live schema:

- **`/verse`** has no county filter, so one request returns every county.
  Freshness checks should cache or save that response instead of calling it per lookup.
- **`/parcels/typeahead`** is a Regrid Enterprise product. With trial tokens, data is
  restricted to 7 counties.
- **`/parcels/path`** is documented as best used together with typeahead: typeahead
  finds the parcel path, and `/parcels/path` fetches the record.
- **`/schemas/*`** have no security requirement in the spec (`security: []`), so they
  need no token. Through MCP, they still go through `execute-request`, so they count
  against the request budget.

## Options the skill switches off or ignores

- **Premium datasets:** `return_zoning`, `return_enhanced_ownership`,
  `return_matched_buildings` and `return_matched_addresses`. The skill disables them
  unless the user asks, and gives no guidance on when they are worth requesting.
  Enhanced ownership can go past an LLC name, which matters because the skill already
  separates recorded owners from beneficial owners.
- **`return_count`:** counts matching parcels without returning records. Useful for
  setting a record budget on open-ended searches before pulling records.
- **`offset_id`:** pages through results beyond the first page.

## CLI: not used by the plugin

- In Claude Code, the plugin always goes through MCP (`npx mcp-remote` with the token
  in a header). It never uses the local `regrid` CLI, which could run lookups with the
  token loaded from `.env` into that one command (`uv run --env-file .env --no-sync regrid ...`).
- The repo's catalog of 169 US parcel fields (`src/regrid/parcel_fields.py`), with each
  field's type, tier and source, is not shipped as a skill reference.
- Tile commands (`tilejson`, `tile`, `grid`) are not used.

## Left out on purpose (recommend keeping it that way)

- `/report`: a POST that files a data issue with Regrid.
- `/client_token/typeahead`: creates a temporary token.
- Regrid tile overlays in the map page: they would put a token in the page.
- Canadian routes, Regrid Global and the Batch API (out of project scope).

## Improvement ideas

1. **County freshness check** (`/verse`): report when Regrid last refreshed the county,
   and warn when it is stale. One request returns every county, so cache the response.
2. **Address cleanup** (`/parcels/typeahead` then `/parcels/path`): resolve an ambiguous
   or mistyped address before a lookup that uses up records. This needs a Regrid
   Enterprise token; trial tokens cover only 7 counties.
3. **Field explanations** (`/schemas/*` and the field catalog): explain what returned
   fields and codes mean.
4. **Premium dataset guidance:** when zoning, enhanced ownership or building data is
   worth requesting, and what each costs.
5. **Count before pulling** (`return_count`) and **paging** (`offset_id`) for
   open-ended searches.
6. **CLI executor for Claude Code:** an alternative to MCP when the CLI and `.env`
   are available.
7. **One command for the usual flow:** address, then property data, then the satellite map.
8. **Neighbouring parcel outlines on the map** (a point or radius search with
   geometry; costs extra records).
9. **Spreadsheet or GeoJSON export** of results. The satellite map design listed GIS
   export files as a non-goal, so this would reverse that decision.
10. **Windows CI job** for the bundled helpers.
11. **One authorised live lookup** to confirm that address responses include the
    parcel outline by default (an open risk from the satellite map design).

## Open question

Which of these matter depends on what the lookups are for: when a property and its
map are pulled up, what is the user usually trying to find out or decide?
