# Todos

Scope is US parcels only. Each item that changes the plugin needs regression tests, a
changelog entry and a plugin version bump. Items marked **decision** need the owner's
answer before building; items marked **authorization** need explicit permission for a
billable or credentialed call.

## Open (Regrid Research 0.9.6 / SDK 0.4.5)

Needs the owner (billable, credentialed, or host apps):
- [ ] **Model evaluations** (**authorization**: model-billed): run the discovery, feature
  and composition evals in `plugins/regrid-research/evals/` against a real model. They are
  the only check that the skill routes and behaves correctly; release checks only
  validate fixture structure.
- [ ] **Map in the real hosts**: open `/regrid-research:address-map` once each in Claude
  Code, the Claude apps and Cowork to confirm that unpkg (Leaflet) and the Esri imagery
  load in those hosts' pages, and record `verified` or `failed` in
  `evals/results/map-hosts-0.9.6.json` (map render was verified in a plain browser on
  `0.9.3`; all three host checks remain `not_run`).
- [ ] **Live `/mcp` connection** (**authorization**): exercise the plugin's real path,
  Regrid's MCP server, end to end, including POST geometry search over MCP and POST area
  `return_parcels` (live checks so far used the SDK and CLI, and verified `return_parcels`
  on POST point only).

Features (when wanted):
- [ ] **Offline field lookups for other schemas**: snapshot `zoning`, `building`,
  `address` and `enhanced_ownership` fields like the parcel catalog so they do not need
  a `/schemas/*` request.
- [ ] **Optional new commands**: `owner-portfolio` (count first, then page an owner
  search to CSV within a budget) and `county-freshness`.

Watch:
- Keep `property-research/SKILL.md` under its 950-word cap (`tests/test_claude_plugins.py`);
  the next real feature needs guidance moved into a reference first.

## Not doing (left out on purpose)

- `/report` (files a data issue with Regrid) and `/client_token/typeahead` (creates a
  temporary token).
- Regrid tile overlays inside the map page (would put a token in the page).
- Canadian routes beyond existing SDK support, Regrid Global and the Batch API.
