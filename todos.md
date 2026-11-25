# Todos

Scope is US parcels only. Each item that changes the plugin needs regression tests, a
changelog entry and a plugin version bump. Items marked **decision** need the owner's
answer before building; items marked **authorization** need explicit permission for a
billable or credentialed call.

Ranked highest to lowest priority across verification gaps (`P0`–`P1`) and optional
features/polish (`P2`–`P3`).

## Open (Regrid Research 0.9.7 / SDK 0.5.0)

### P0 — Unverified core behavior (highest risk)

1. [ ] **Model evaluations** (**authorization**: model-billed):
   run the discovery (`run_discovery_claude.py`), feature, and composition evals in
   `plugins/regrid-research/evals/` against a real Claude model and grade against rubrics.
   Release checks validate fixture structure only (`27` synthetic fixtures); no real model
   behavior check has run since `0.5.0`.

### P1 — Map & host verification after `0.9.7` `map.py` hardening

2. [ ] **Synthetic plain-browser map render check for `0.9.7`** *(zero API cost, unblocked)*:
   render a synthetic US response + neighbours via `regrid map --neighbours` and confirm
   Leaflet, Esri imagery, outlines, info panel, attribution, and clean console in a local
   browser. Unlike `0.9.4`–`0.9.6`, `0.9.7` modified `map.py` on the `render()` path
   (`_load_json`, `_check_and_prune`, `_json_for_script`), so the `0.9.3` browser baseline
   no longer covers identical code.
3. [ ] **Real-host plugin & map checks** *(manual host apps; **authorization** for live lookup)*:
   verify plugin loading, MCP host connector auth, and `/regrid-research:address-map` once
   each in Claude Code, the Claude apps, and Cowork (confirming `unpkg.com` Leaflet and Esri
   imagery load under each host's CSP/sandbox), and record `verified` or `failed` in
   `plugins/regrid-research/evals/results/map-hosts-0.9.7.json` (all three hosts remain
   `not_run`). Direct Streamable HTTP `/mcp` transport (`GET /usage` + `POST /parcels/area`
   `return_parcels=true`) and SDK `0.5.0` `make live` were verified on 2026-11-24; host UI
   import and Cowork header support remain unverified.

### P2 — Optional feature additions (when wanted)

4. [ ] **`owner-portfolio` command** (**decision**):
   count matching parcels first, then page results to CSV within an agreed budget.
   *Constraint:* `/parcels/owner` supports neither `return_count` nor `offset_id` paging, so
   this command must use `/parcels/query` with `fields[owner][ilike]` (queryable in
   `parcel_fields.json`) plus a geographic scope (`path` or `geojson`). Confirm whether
   substring matching via `/parcels/query` (`owner` is partially standardized) matches the
   intended workflow before building.
5. [ ] **Offline field catalogs for non-parcel schemas**:
   snapshot `/schemas/zoning` (26 fields), `/schemas/building` (19 fields), `/schemas/address`
   (37 fields), and `/schemas/enhanced_ownership` (60 fields) alongside `parcel_fields.json`
   so `fields.py` / `regrid fields` can answer addon field questions without spending a
   `/schemas/*` request (4 public schema fetches at snapshot time; no parcel charges).
6. [ ] **`county-freshness` command** (**decision**):
   wrap county freshness lookup as a plugin command.
   *Constraint:* `/verse` is CLI-only (`regrid freshness`) and forbidden over MCP, while
   `plugins/regrid-research/commands/` ships in both Claude Code and Cowork archives. Decide
   whether a Cowork-shared command is worth adding (offline-only via a user-supplied `/verse`
   JSON on Cowork; `regrid freshness` on Claude Code).

### P3 — Optional directory polish

7. [ ] **Plugin icon (`ICON_MISSING` warning)** *(only if submitting to Claude's plugin directory)*:
   add a square PNG (512–2048 px, <2 MB) at `plugins/regrid-research/.claude-plugin/icon.png`
   to clear the non-blocking `ICON_MISSING` warning from `claude plugin validate --strict`.

## Recently completed

- [x] **Live `/mcp` connection & SDK `0.5.0` smoke check** (2026-11-24, authorized):
  `make live` passed on SDK `0.5.0` (169 schema definitions, 0 type differences, geometry
  present, observed delta 1); direct Streamable HTTP `/mcp` against
  `https://support.regrid.com/mcp` with `x-regrid-token` verified `tools/list` (`tools.json`
  parity), `list-specs`, authenticated `GET /usage`, and `POST /parcels/area` with
  `return_parcels=true` (`limit=1`, returning `area` + 1 parcel feature with geometry and
  fields). Claude Code / Cowork host UI import remains tracked in P1 #3.

## Watch

- Keep `property-research/SKILL.md` under its 950-word cap (`tests/test_claude_plugins.py`;
  currently **786 words**, 164 words of headroom); move verbose guidance into references when
  adding features.

## Not doing (left out on purpose)

- `/report` (files a data issue with Regrid) and `/client_token/typeahead` (creates a
  temporary token) in the plugin research skill.
- Regrid tile overlays inside the map page (would expose a token in the page).
- Canadian routes beyond existing SDK support, Regrid Global, and the Batch API.
