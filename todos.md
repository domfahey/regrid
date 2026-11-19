# Todos

Work identified by the [plugin feature audit](docs/plugin-feature-audit-2026-11-19.md).
Scope is US parcels only. Each item that changes the plugin needs regression tests, a
changelog entry and a plugin version bump. Items marked **decision** need the owner's
answer before building; items marked **authorization** need explicit permission for a
billable or credentialed call.

## Priority

Impact is judged against the main workflow: look up a US property by street address,
pull its data and boundary, and view it on an interactive satellite map. Size is
relative:
- **XS:** a single check or doc edit.
- **S:** one small PR, mostly docs or skill text plus tests.
- **M:** new helper code or several references.
- **L:** a new execution path with security and budget rules.

| # | Todo | Impact | Size | Why this rank |
| --- | --- | --- | --- | --- |
| 1 | Live outline check | High | XS | The map feature rests on it; one lookup settles the open risk (**authorization**) |
| 2 | One command for the usual flow | High | S | Turns the main workflow into one step |
| 3 | Map in Claude apps and Cowork | High | XS | If the map doesn't load there, those hosts need a fallback |
| 4 | Premium dataset guidance | Medium | S | Docs only; makes zoning and enhanced ownership usable when asked |
| 5 | Ship the US parcel field catalog | Medium | S | The generator already exists; explains fields at no request cost |
| 6 | Refresh by Regrid path | Medium | S | Cheap, exact re-fetch of a saved property |
| 7 | Windows CI job | Medium | S | Guards the bundled helpers on a platform only simulated so far |
| 8 | County freshness (`/verse`) | Medium | M | Adds trust in the data date, but needs caching (one call returns all counties) (dates only; no stale label) |
| 9 | Address suggestions then fetch by path | Medium | M | Helps mistyped addresses, but Enterprise-only, so many tokens can't use it |
| 10 | Neighbouring parcel outlines | Medium | M | Useful map context, but costs extra records (**decision**: radius and cap) |
| 11 | Count before pulling (`return_count`) | Low | S | Matters for open-ended searches, not single-address lookups |
| 12 | Field definitions (`/schemas/*`) | Low | S | Mostly covered by the field catalog (#5) |
| 13 | Detailed usage (`/usage/detailed`) | Low | S | Nice for "lookups left" questions |
| 14 | Tile commands documented as CLI-only | Low | XS | Docs clarity only |
| 15 | Paging (`offset_id`) | Low | M | Only for large open-ended searches |
| 16 | Spreadsheet or GeoJSON export | Low | M | Reverses a design non-goal (**decision**) |
| 17 | CLI executor for Claude Code | Low | L | MCP already works; adds a second credential path to secure and test |

Suggested batches:
- **Now:** #1–#3. They confirm the map works everywhere and make the main workflow one step.
- **Next:** #4–#7. Small, low-risk improvements.
- **Then:** #8–#10. Each needs a decision or more code.
- **Later:** #11–#17.

## Verification

- [ ] **Live outline check** (**authorization**; code side done: `make live` reports geometry present/null/absent; awaiting user: not run): with one live address lookup,
  confirm the response includes the parcel outline (`geometry`) by default. This is
  the open risk from the satellite map design. If the outline is missing, revisit
  `references/map.md`.
- [x] **Windows CI job** (passing on PR #6, merged 2026-11-19): run `tests/test_regrid_map.py` and the workflow-helper tests
  on Windows. This covers `os.open` with `O_BINARY`, `os.link` and its fallback, and
  `python3` versus `py`.
- [ ] **Map in Claude apps and Cowork** (map render verified in a plain browser 2026-11-19, see `evals/results/map-hosts-0.8.0.json`; Claude Code, Claude apps and Cowork hosts awaiting user: not run): confirm that unpkg (Leaflet) and the Esri
  imagery load in those hosts' pages, and record the result.

## New lookups (MCP and CLI both offer these; the skill does not use them)

- [x] **County freshness (`/verse`)**:
  - Report when Regrid last did a full pull for the parcel's county, and report the dates only (never label a county stale).
  - One request returns every county, so save the response and reuse it within a task
    or across checkpoints instead of calling it for each property.
  - Add it to `endpoints.json` and to the endpoint table in `mcp-tools.md`.
- [x] **Address suggestions (`/parcels/typeahead`) then fetch by path (`/parcels/path`)**:
  - Use when an address is ambiguous or mistyped, before spending records on a lookup.
  - Typeahead is a Regrid Enterprise product (trial tokens cover only 7 counties), so
    the skill must handle "not available on this token" without retrying.
  - Each call counts against the request budget.
  - Add both endpoints to `endpoints.json` and `mcp-tools.md`.
- [x] **Refresh by Regrid path (`/parcels/path`)**: re-fetch a saved result by its
  `path` when the user asks to refresh or the result is shown to be stale. Wire it
  into `references/batch.md` resume rules.
- [x] **Field definitions (`/schemas/*`)**:
  - Explain what returned fields and codes mean (`usedesc`, zoning, building, address,
    enhanced ownership).
  - No token is needed, but through MCP each call still counts as a request, so
    prefer the bundled field catalog below and call the schema endpoints only for
    fields it lacks.

## Options the skill ignores

- [x] **Premium dataset guidance**:
  - Say when `return_zoning`, `return_enhanced_ownership`, `return_matched_buildings`
    and `return_matched_addresses` are worth requesting, and that they need user
    authorization.
  - Enhanced ownership ties into the existing recorded-versus-beneficial-owner rules.
- [x] **Count before pulling (`return_count`)**: for open-ended owner, area, point and
  query searches, count matches first so a record budget can be agreed. The count
  call still counts against the request budget.
- [x] **Paging (`offset_id`)** (implemented as `--max-records`; the cursor field is unverified live, awaiting user: not run): page through results within an agreed record budget,
  Paging positions are NOT carried through checkpoints; a resumed open-ended search
  needs fresh authorization.
- [x] **Detailed usage (`/usage/detailed`)**: consider it for setup or "how many
  lookups do I have left" questions. Never request per-token breakdowns.

## CLI and repo assets

- [x] **CLI executor for Claude Code**:
  - Allow lookups through the local `regrid` CLI (`uv run --env-file .env --no-sync regrid ...`)
    when MCP is unavailable or for file outputs.
  - The token stays in the child process; never display or inspect it, and never put
    token-bearing URLs in output.
  - Apply the same request ledger and budget rules as MCP.
  - Not for Cowork or the Claude apps.
- [x] **Ship the US parcel field catalog**: generate a compact reference from
  `src/regrid/parcel_fields.py` (169 fields: name, type, tier, meaning) and add a test
  that the generated file stays current.
- [x] **Tile commands (`tilejson`, `tile`, `grid`)**: document them as CLI-only. Keep
  tiles out of the map page, because tile overlays need a token.

## Workflow and map

- [x] **One command for the usual flow**: a plugin command that takes an address, runs
  the lookup, reports the property data and renders the satellite map, within one
  request and one record by default.
- [x] **Neighbouring parcel outlines** (**decision**): draw nearby parcels on the map
  from a point or radius search with `return_geometry=true`. This costs extra
  requests and records, so decide on the default radius and record cap.
- [x] **Spreadsheet or GeoJSON export** (**decision**): export results as CSV and
  boundaries as GeoJSON. The satellite map design listed GIS export files as a
  non-goal, so this reverses that decision.

## Not doing (left out on purpose)

- `/report` (files a data issue with Regrid) and `/client_token/typeahead` (creates a
  temporary token).
- Regrid tile overlays inside the map page (would put a token in the page).
- Canadian routes beyond existing SDK support, Regrid Global and the Batch API.
