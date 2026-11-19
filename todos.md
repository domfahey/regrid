# Todos

Work identified by the [plugin feature audit](docs/plugin-feature-audit-2026-11-19.md).
Scope is US parcels only. Each item that changes the plugin needs regression tests, a
changelog entry and a plugin version bump. Items marked **decision** need the owner's
answer before building; items marked **authorization** need explicit permission for a
billable or credentialed call.

## Verification

- [ ] **Live outline check** (**authorization**): with one live address lookup,
  confirm the response includes the parcel outline (`geometry`) by default. This is
  the open risk from the satellite map design. If the outline is missing, revisit
  `references/map.md`.
- [ ] **Windows CI job**: run `tests/test_regrid_map.py` and the workflow-helper tests
  on Windows. This covers `os.open` with `O_BINARY`, `os.link` and its fallback, and
  `python3` versus `py`.
- [ ] **Map in Claude apps and Cowork**: confirm that unpkg (Leaflet) and the Esri
  imagery load in those hosts' pages, and record the result.

## New lookups (MCP and CLI both offer these; the skill does not use them)

- [ ] **County freshness (`/verse`)**:
  - Report when Regrid last did a full pull for the parcel's county, and flag it when stale.
  - One request returns every county, so save the response and reuse it within a task
    or across checkpoints instead of calling it for each property.
  - Add it to `endpoints.json` and to the endpoint table in `mcp-tools.md`.
  - **Decision:** how many days old counts as stale.
- [ ] **Address suggestions (`/parcels/typeahead`) then fetch by path (`/parcels/path`)**:
  - Use when an address is ambiguous or mistyped, before spending records on a lookup.
  - Typeahead is a Regrid Enterprise product (trial tokens cover only 7 counties), so
    the skill must handle "not available on this token" without retrying.
  - Each call counts against the request budget.
  - Add both endpoints to `endpoints.json` and `mcp-tools.md`.
- [ ] **Refresh by Regrid path (`/parcels/path`)**: re-fetch a saved result by its
  `path` when the user asks to refresh or the result is shown to be stale. Wire it
  into `references/batch.md` resume rules.
- [ ] **Field definitions (`/schemas/*`)**:
  - Explain what returned fields and codes mean (`usedesc`, zoning, building, address,
    enhanced ownership).
  - No token is needed, but through MCP each call still counts as a request, so
    prefer the bundled field catalog below and call the schema endpoints only for
    fields it lacks.

## Options the skill ignores

- [ ] **Premium dataset guidance**:
  - Say when `return_zoning`, `return_enhanced_ownership`, `return_matched_buildings`
    and `return_matched_addresses` are worth requesting, and that they need user
    authorization.
  - Enhanced ownership ties into the existing recorded-versus-beneficial-owner rules.
- [ ] **Count before pulling (`return_count`)**: for open-ended owner, area, point and
  query searches, count matches first so a record budget can be agreed. The count
  call still counts against the request budget.
- [ ] **Paging (`offset_id`)**: page through results within an agreed record budget,
  carrying the paging position through checkpoints.
- [ ] **Detailed usage (`/usage/detailed`)**: consider it for setup or "how many
  lookups do I have left" questions. Never request per-token breakdowns.

## CLI and repo assets

- [ ] **CLI executor for Claude Code**:
  - Allow lookups through the local `regrid` CLI (`uv run --env-file .env --no-sync regrid ...`)
    when MCP is unavailable or for file outputs.
  - The token stays in the child process; never display or inspect it, and never put
    token-bearing URLs in output.
  - Apply the same request ledger and budget rules as MCP.
  - Not for Cowork or the Claude apps.
- [ ] **Ship the US parcel field catalog**: generate a compact reference from
  `src/regrid/parcel_fields.py` (169 fields: name, type, tier, meaning) and add a test
  that the generated file stays current.
- [ ] **Tile commands (`tilejson`, `tile`, `grid`)**: document them as CLI-only. Keep
  tiles out of the map page, because tile overlays need a token.

## Workflow and map

- [ ] **One command for the usual flow**: a plugin command that takes an address, runs
  the lookup, reports the property data and renders the satellite map, within one
  request and one record by default.
- [ ] **Neighbouring parcel outlines** (**decision**): draw nearby parcels on the map
  from a point or radius search with `return_geometry=true`. This costs extra
  requests and records, so decide on the default radius and record cap.
- [ ] **Spreadsheet or GeoJSON export** (**decision**): export results as CSV and
  boundaries as GeoJSON. The satellite map design listed GIS export files as a
  non-goal, so this reverses that decision.

## Not doing (left out on purpose)

- `/report` (files a data issue with Regrid) and `/client_token/typeahead` (creates a
  temporary token).
- Regrid tile overlays inside the map page (would put a token in the page).
- Canadian routes beyond existing SDK support, Regrid Global and the Batch API.
