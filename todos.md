# Todos

Scope is US parcels only. Each item that changes the plugin needs regression tests, a
changelog entry and a plugin version bump. Items marked **decision** need the owner's
answer before building; items marked **authorization** need explicit permission for a
billable or credentialed call.

Ranked highest to lowest priority across verification gaps (`P0`–`P1`) and optional
features/polish (`P2`–`P3`).

## Open (Regrid Research 0.9.7 / SDK 0.5.0)

### P0 — Unverified core behavior (highest risk)

1. [ ] **Live `/mcp` connection & SDK `0.5.0` smoke check** (**authorization**: credentialed, may incur parcel charges):
   exercise the plugin's real transport (`https://support.regrid.com/mcp`) end to end,
   including POST geometry search over MCP and whether `POST /parcels/area` accepts
   `return_parcels=true` (live checks so far used SDK/CLI only on `0.4.4`/`0.4.5` and
   verified `return_parcels` on POST point only). Optionally re-run `make live` / `make live-full`
   against SDK `0.5.0` to verify the `live_full.py` fixes and `regrid tile --replace`.
2. [ ] **Model evaluations** (**authorization**: model-billed):
   run the discovery (`run_discovery_claude.py`), feature, and composition evals in
   `plugins/regrid-research/evals/` against a real Claude model and grade against rubrics.
   Release checks validate fixture structure only (`27` synthetic fixtures); no real model
   behavior check has run since `0.5.0`.

### P1 — Map verification after `0.9.7` `map.py` hardening

3. [ ] **Synthetic plain-browser map render check for `0.9.7`** *(zero API cost, unblocked)*:
   render a synthetic US response + neighbours via `regrid map --neighbours` and confirm
   Leaflet, Esri imagery, outlines, info panel, attribution, and clean console in a local
   browser. Unlike `0.9.4`–`0.9.6`, `0.9.7` modified `map.py` on the `render()` path
   (`_load_json`, `_check_and_prune`, `_json_for_script`), so the `0.9.3` browser baseline
   no longer covers identical code.
4. [ ] **Map in the real hosts** *(manual host apps)*:
   open `/regrid-research:address-map` once each in Claude Code, the Claude apps, and Cowork
   to confirm that `unpkg.com` (Leaflet) and Esri imagery load under each host's CSP/sandbox,
   and record `verified` or `failed` in `plugins/regrid-research/evals/results/map-hosts-0.9.7.json`
   (all three hosts remain `not_run`).

### P2 — Optional feature additions (when wanted)

5. [ ] **`owner-portfolio` command** (**decision**):
   count matching parcels first, then page results to CSV within an agreed budget.
   *Constraint:* `/parcels/owner` supports neither `return_count` nor `offset_id` paging, so
   this command must use `/parcels/query` with `fields[owner][ilike]` (queryable in
   `parcel_fields.json`) plus a geographic scope (`path` or `geojson`). Confirm whether
   substring matching via `/parcels/query` (`owner` is partially standardized) matches the
   intended workflow before building.
6. [ ] **Offline field catalogs for non-parcel schemas**:
   snapshot `/schemas/zoning` (26 fields), `/schemas/building` (19 fields), `/schemas/address`
   (37 fields), and `/schemas/enhanced_ownership` (60 fields) alongside `parcel_fields.json`
   so `fields.py` / `regrid fields` can answer addon field questions without spending a
   `/schemas/*` request (4 public schema fetches at snapshot time; no parcel charges).
7. [ ] **`county-freshness` command** (**decision**):
   wrap county freshness lookup as a plugin command.
   *Constraint:* `/verse` is CLI-only (`regrid freshness`) and forbidden over MCP, while
   `plugins/regrid-research/commands/` ships in both Claude Code and Cowork archives. Decide
   whether a Cowork-shared command is worth adding (offline-only via a user-supplied `/verse`
   JSON on Cowork; `regrid freshness` on Claude Code).

### P3 — Optional directory polish

8. [ ] **Plugin icon (`ICON_MISSING` warning)** *(only if submitting to Claude's plugin directory)*:
   add a square PNG (512–2048 px, <2 MB) at `plugins/regrid-research/.claude-plugin/icon.png`
   to clear the non-blocking `ICON_MISSING` warning from `claude plugin validate --strict`.

## Watch

- Keep `property-research/SKILL.md` under its 950-word cap (`tests/test_claude_plugins.py`;
  currently **786 words**, 164 words of headroom); move verbose guidance into references when
  adding features.

## Not doing (left out on purpose)

- `/report` (files a data issue with Regrid) and `/client_token/typeahead` (creates a
  temporary token) in the plugin research skill.
- Regrid tile overlays inside the map page (would expose a token in the page).
- Canadian routes beyond existing SDK support, Regrid Global, and the Batch API.
