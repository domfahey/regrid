# Todos

Scope is US parcels only. Each item that changes the plugin needs regression tests, a
changelog entry and a plugin version bump. Items marked **decision** need the owner's
answer before building; items marked **authorization** need explicit permission for a
billable or credentialed call.

Ranked highest to lowest priority across verification gaps (`P0`–`P1`) and optional
features/polish (`P2`–`P3`).

## Open (Regrid Research 0.9.7 / SDK 0.5.0)

### P0 — Gaps found by 0.9.7 real-model evaluations

1. [ ] **Fix `freshness_mcp_only` parcel-vs-county wording gap** *(failed on `claude-sonnet-5-5`, 2/4 criteria)*:
   `src/regrid/data/parcel_fields.json` (and generated `references/fields.json`) describes
   `ll_last_refresh` as `"Last date Regrid refreshed county data"`, and `references/cli.md`
   does not warn against generalizing a single parcel's `ll_last_refresh` to county-wide
   freshness — causing Sonnet to present the parcel date as the whole county's refresh date.
   Clarify the field/reference wording and rerun `feature` evals.
2. [ ] **Resolve discovery harness & `trigger_13` mismatches** (**decision** on `trigger_13`):
   - `trigger_13` (`"Who owns 100 Queen Street West, Toronto?"`): both Haiku and Sonnet
     returned `none` (16/17) because `SKILL.md` frontmatter specifies US properties, whereas
     `trigger-cases.json` expects `property-research`. Decide whether out-of-scope non-US
     prompts should expect `none` or trigger `property-research` for an explicit refusal.
   - Discovery harness (`run_discovery_claude.py` / `discovery.py`): default
     `--max-budget-usd 0.25` capped `opus-structured-handoff-skill` at `$0.2644`
     (`error_max_budget_usd`) right after reading all 5 relevant files (making that trial
     `INCOMPLETE`), and `discovery.py compare()` marks pairs `comparable` without checking
     trial completion status.
   - `checkpoint-correction` skill discovery: all 3 models (Haiku, Sonnet, Opus) skipped
     `skills/property-research/SKILL.md` when `support/workflow.py` was already provided in
     `task_dependencies` (and `SKILL.md` frontmatter does not mention checkpoint/handoff
     validation; Haiku also skipped `SKILL.md` on `existing-evidence` and
     `structured-handoff`). Decide whether to mention handoffs/checkpoints in `SKILL.md`
     frontmatter or revise the discovery staging/rubric, then retest.

### P1 — Map & host verification after `0.9.7` `map.py` hardening

3. [ ] **Synthetic plain-browser map render check for `0.9.7`** *(zero API cost, unblocked)*:
   render a synthetic US response + neighbours via `regrid map --neighbours` and confirm
   Leaflet, Esri imagery, outlines, info panel, attribution, and clean console in a local
   browser. Unlike `0.9.4`–`0.9.6`, `0.9.7` modified `map.py` on the `render()` path
   (`_load_json`, `_check_and_prune`, `_json_for_script`), so the `0.9.3` browser baseline
   no longer covers identical code.
4. [ ] **Real-host plugin & map checks** *(manual host apps; **authorization** for live lookup)*:
   verify plugin loading, MCP host connector auth, and `/regrid-research:address-map` once
   each in Claude Code, the Claude apps, and Cowork (confirming `unpkg.com` Leaflet and Esri
   imagery load under each host's CSP/sandbox), and record `verified` or `failed` in
   `plugins/regrid-research/evals/results/map-hosts-0.9.7.json` (all three hosts remain
   `not_run`). Direct Streamable HTTP `/mcp` transport (`GET /usage` + `POST /parcels/area`
   `return_parcels=true`) and SDK `0.5.0` `make live` were verified on 2026-11-24; host UI
   import and Cowork header support remain unverified.

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

## Recently completed

- [x] **Real-model offline evaluations for `0.9.7`** (2026-11-24, authorized, `live_calls=0`,
  Claude CLI `2.1.331`, total model cost `$2.5842`):
  fixed macOS Keychain auth in `run_discovery_claude.py` (preserving OS identity/profile
  vars), ran all five suites across `claude-haiku-5-5`, `claude-sonnet-5-5`, and
  `claude-opus-5-5`, and independently graded every transcript against its rubric (saved in
  `plugins/regrid-research/evals/results/model-eval-0.9.7-report.json` with unedited
  transcripts). Results: Research `13/13` PASS (`40/40` criteria); Composition `5/6` PASS
  (`22/23` criteria, `5/5` handoffs valid against `result.schema.json` + `workflow.py`;
  `composition_report` wrote 4 sentences instead of 2); Feature `7/8` PASS (`34/36`
  criteria; `freshness_mcp_only` failed); Triggers `16/17` on Haiku & Sonnet (`trigger_13`
  Toronto); Discovery `23/24` completed + `1` budget-capped (`opus-structured-handoff-skill`,
  `$0.2644` > `$0.25`), `0` critical failures / `0` outside reads — Skill grades: Haiku
  `1/4`, Sonnet `3/4`, Opus `2/4` (`1` FAIL, `1` INCOMPLETE); Baseline grades: Haiku `3/4`,
  Sonnet `4/4`, Opus `4/4`. Actionable gaps are tracked in P0 #1–#2 above.
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
