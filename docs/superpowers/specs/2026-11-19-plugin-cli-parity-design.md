# Plugin and CLI Feature Parity: Design

Date: 2026-11-19. Status: draft for approval. Scope: US parcels only.
Source: [feature audit](../../plugin-feature-audit-2026-11-19.md) and [todos](../../../todos.md).

## Intent

The usual task is to look up a US property by street address, pull its data and
boundary, and explore it on an interactive satellite map. The audit found that the
Regrid Research skill uses about two-thirds of the US API, ignores several useful
options, and shares nothing with the repo's CLI. This project builds every audit todo
in both places:
- **The skill**, used through the Regrid MCP server in Claude Code, Cowork and the Claude apps.
- **The `regrid` CLI**, used in a terminal or by Claude Code.

Each feature should behave the same in both.

## Goals

- Every todo in `todos.md` is built, or is checked and its result recorded.
- Each feature works the same way from the skill and from the CLI, built on shared,
  tested code.
- Red-green TDD throughout: every behavior change starts with a failing test.
- Delivery in four batches (Now, Next, Then, Later, as ranked in `todos.md`). Each batch
  is its own plan, branch and PR, and can ship on its own.

## Non-goals

- Non-US data: Canadian routes beyond existing SDK support, Regrid Global, the Batch API.
- `/report` and `/client_token/typeahead`, as today.
- Regrid tile overlays in the map page, because they would put a token in the page.
- Typed SDK model changes beyond what new CLI commands need.

## Anti-goals (failure even if it "works")

- A token, header or token-bearing URL in any page, export, cache, log, report or
  skill output. Never display or inspect the token.
- Any request that bypasses the shared request and record budget, including counts,
  schema calls, freshness and neighbour lookups.
- Spending records or requests the user did not authorize. Neighbours are off by
  default; extra paid datasets are off unless requested.
- Two diverging implementations of the same helper.
- Labelling a skipped, blocked or manual gate as passed.

## Constraints

- Shared helpers are Python 3.10+ and use only the standard library. Each is a single
  self-contained file with no imports from `regrid`.
- The plugin and the SDK/CLI keep independent versions. Each batch bumps the plugin's
  minor version when the plugin changes, and the SDK's minor version when the CLI
  gains commands.
- Existing CLI commands, JSON output and handoff schemas stay compatible. No result
  schema change in this project (see Paging).
- Ordinary tests never contact Regrid. Live calls happen only in opt-in `make live`
  with the user's authorization.
- Follow AGENTS.md: Conventional Commits; update the changelog and docs; keep generated
  ZIPs out of commits.

## Decisions made

| Decision | Choice |
| --- | --- |
| Code sharing | One source in `src/regrid/offline/`, copied into the skill's `scripts/`. A sync script writes the copies and a test fails if they differ. |
| County freshness | Report the date only; never label data stale. |
| Neighbouring outlines | Off unless asked. When asked: one point search, 100 m radius, at most 25 parcels, with the cost stated before the call. |
| Export | CSV (property data) and GeoJSON (boundaries), reversing the satellite map design's non-goal. |

## Approaches considered for code sharing

- **A. One source, copied (chosen).** Helpers live in `src/regrid/offline/`, standard
  library only. `scripts/sync_skill_helpers.py` copies them into the skill;
  `tests/test_skill_helper_sync.py` asserts the files are byte-identical. The CLI
  imports them as normal modules.
- B. The CLI imports the skill file. Rejected: an installed package cannot rely on the
  plugin folder.
- C. Separate implementations. Rejected: they would drift apart and need duplicate tests.

## Design

### Shared offline helpers (`src/regrid/offline/`, copied to `skills/property-research/scripts/`)

- **`map.py`**: moved from the skill unchanged, then extended:
  - `render ... --neighbours NEIGHBOURS.json` draws neighbouring parcels in a muted
    style beneath the subject parcel. It excludes the subject by `ll_uuid`, validates
    neighbour geometry, and skips the area check for neighbours.
  - `export RESPONSE [--csv OUT.csv] [--geojson OUT.geojson] [--replace]` writes the
    exports below. It reuses the same validation and the same no-overwrite atomic
    writes.
- **`export` formats:**
  - **CSV:** one row per feature, with fixed core columns: `headline`, `path`,
    `ll_uuid`, `owner`, `parcelnumb`, `ll_last_refresh`, `ll_gisacre`, `ll_gissqft`,
    `lat`, `lon`. `--all-fields` adds every field, sorted by name. Missing values are
    empty cells. Cells starting with `=`, `+`, `-` or `@` are prefixed with `'` so
    spreadsheets do not run them as formulas.
  - **GeoJSON:** a FeatureCollection of the validated features, with geometry exactly
    as received plus the same core properties.
- **`freshness.py`**: `freshness.py county VERSE.json --path /us/nj/camden` (or
  `--state nj --county camden`) prints the county's last full-pull date and source
  fields from a saved `/verse` response. Offline, date only.
- **`fields.py`**: `fields.py explain FIELD...` and `fields.py search TERM` read a
  compact `references/fields.json`. That file is generated from
  `src/regrid/data/parcel_fields.json` (169 US fields: name, type, tier, description),
  and a test keeps it current.

`workflow.py` stays skill-only; the CLI does not need it.

### New CLI commands (`src/regrid/cli.py`)

Existing commands are unchanged. New commands:

| Command | Requests | Behavior |
| --- | --- | --- |
| `regrid map RESPONSE OUTPUT [map options]` | 0 | Runs the offline map renderer |
| `regrid export RESPONSE [--csv F] [--geojson F] [--all-fields]` | 0 | Runs the offline exporter |
| `regrid fields explain/search ...` | 0 | Offline field catalog |
| `regrid freshness --path /us/<st>/<county> [--cache F] [--refresh]` | 0 or 1 | Calls `/verse` with `return_geometry=false`, caches the response and reuses the cache unless `--refresh`; prints date and cache age |
| `regrid address-map ADDRESS OUTPUT [--path SCOPE] [--neighbours] [--save-response F]` | 1 (+1 with `--neighbours`) | Address lookup with `limit=1` and paid datasets off, saves the response, renders the map; `--neighbours` adds the 100 m / 25-parcel point search |
| `--max-records N` on `owner`, `area`, `point`, `query` | ceil(N / limit) | Follows `offset_id` until N records or the end, then reports how many requests it made |

- **Freshness cache:** the default location is the user cache directory
  (`~/.cache/regrid/verse.json`, or `%LOCALAPPDATA%` on Windows). It holds only the
  verse response and its retrieval time, never the token.
- **Request summaries:** commands that make requests print a summary of requests made
  to stderr, so callers can account for them.
- **Already covered:** `return_count`, `typeahead`, `parcel-path`, `schema` and
  `usage --detailed` already work. They get help text and README examples only.

### Skill changes

- **MCP references:**
  - Regenerate `endpoints.json` from the live documentation tools (free calls) to add
    `/parcels/path`, `/parcels/typeahead`, `/verse`, `/schemas/*` and `/usage/detailed`.
  - Add these to the endpoint table in `mcp-tools.md`.
- **Address suggestions:**
  - When an address is ambiguous or mistyped, `/parcels/typeahead` then `/parcels/path`
    resolves it. Each is one request.
  - Typeahead needs an Enterprise token. A permission error is recorded once, never
    retried, and the skill asks the user for clarification instead.
- **Refresh by path:** an explicit refresh of a saved result uses `/parcels/path` with
  the saved `path` (one record). This is documented in `batch.md`.
- **Paid-dataset guidance:** a new `references/premium.md`.
  - When zoning, enhanced ownership, matched buildings or matched addresses answer
    the question.
  - They are requested only with the user's authorization.
  - Enhanced ownership connects to the existing recorded-versus-beneficial-owner rule.
- **Count and paging:**
  - Open-ended searches may first make a `return_count` call (one request, zero
    records) to agree a record budget.
  - Paging with `offset_id` works within one task, inside the budget. Paging
    positions are not saved in checkpoints. A resumed task restarts open-ended
    searches only with fresh authorization, and that limit is documented.
- **Field explanations:** run `fields.py` against the bundled catalog first. Call
  `/schemas/*` (one request each) only for fields the catalog lacks.
- **County freshness:**
  - Each parcel record's `ll_last_refresh` is the default freshness answer and costs
    nothing extra.
  - `/verse` returns every county, which is too large to pass through chat. The skill
    uses it only through the CLI path (`regrid freshness`), which keeps the response
    in a file.
  - Over MCP, the skill reports `ll_last_refresh` and says that county pull dates
    need the CLI.
- **Neighbours:**
  - Only on request. The skill states the cost first, makes one `/parcels/point`
    request (lat/lon from the subject's fields, `radius=100`, `limit=25`,
    `return_geometry=true`), saves it, and runs `map.py render --neighbours`.
- **Export:** `map.py export` from the saved response, with no extra requests.
- **CLI path:** a new `references/cli.md`, Claude Code only.
  - **When:** the `regrid` CLI is on PATH and `REGRID_TOKEN` is already in the
    environment, or the session is inside this repo with `.env`, in which case
    commands run as `uv run --env-file .env --no-sync regrid ...`.
  - **Choosing it:** used when MCP is unavailable or a feature needs files (freshness,
    exports). The skill never reads `.env` or the token.
  - **Budget:** every CLI call that hits the API is a ledger attempt, like an MCP call.
- **One-step command:** a Claude Code plugin command, `commands/address-map.md`.
  - It runs the usual flow: lookup, short property summary, map.
  - It uses one request and one record by default, and passes `--neighbours` only when
    the user includes it.
  - Hosts without plugin commands rely on the skill's normal triggers.
- **Tiles:** a short note in `cli.md` that tile commands are CLI-only and never go in
  the map page.
- **Packaging:** the build ships all shared helpers and `fields.json` in all three
  archives. The discovery eval `ALLOWLIST` includes them.

### Verification items

- **Live outline check** (needs the user's authorization): extend `make live` to report
  `geometry_present` for the looked-up parcel, as a boolean only. Tests use mocked
  responses; the live run happens only when the user runs or authorizes it. If
  geometry is absent, `map.md` is revised before Batch 1 ships.
- **Claude apps and Cowork map check** (manual): a checklist in
  `evals/README.md`, with the result recorded as verified, failed or not run. Never
  claim it passed without evidence.
- **Windows CI:** a `windows-latest` job runs the offline-helper tests and the CLI
  tests that don't need OpenSSL.

## Batches (one plan each)

1. **Now (plugin 0.7.0, SDK 0.2.0):**
   - Shared-helper move and sync test.
   - `regrid map`.
   - `regrid address-map` and the plugin command.
   - Live geometry reporting.
   - Claude apps and Cowork checklist.
2. **Next:**
   - Paid-dataset guidance.
   - Field catalog: `fields.py` and `regrid fields`.
   - Refresh by path.
   - Windows CI.
3. **Then:**
   - County freshness: `freshness.py`, `regrid freshness`, and the freshness part of `cli.md`.
   - Address suggestions.
   - Neighbours: `--neighbours` in both.
4. **Later:**
   - Count and paging: `--max-records`.
   - Schema-backed explanations.
   - Detailed usage.
   - Tile note.
   - Export: `map.py export` and `regrid export`.
   - CLI path for the skill.

## Builder questions settled (my calls, from the builder check)

1. **What `commands/address-map.md` uses:** the skill's MCP flow (lookup, save the
   decoded response verbatim, `scripts/map.py render`). `regrid address-map` is the CLI
   equivalent; the plugin command does not need the CLI.
2. **Neighbours:** Batch 1 ships `address-map` and the plugin command without
   `--neighbours`. Batch 3 adds the flag to the CLI, the skill flow and the command.
3. **Ledger for CLI calls:** the CLI stays ledger-unaware and only prints its stderr
   request summary.
   - The skill reserves a ledger attempt before each CLI command that can hit the API,
     and completes it from that summary.
   - An unreadable summary leaves the attempt uncertain.
   - Batch 3 adds the freshness part of `cli.md`; Batch 4 completes it.
4. **Geometry on `address-map`:** `/parcels/address` has no `return_geometry` option,
   so the command sends none. If a response lacks geometry, `map.py` already exits 1
   with "omits geometry". The Batch 1 live check settles whether geometry is returned.
5. **If the live check is not authorized:** Batch 1 can still ship with the live check
   reported as "not run" in the PR and changelog, never as passed. The missing-geometry
   failure is already handled.
6. **Response shape:** the CLI prints the raw API response body. A decoded MCP
   `execute-request` response is the same body. `map.py` is unchanged, and a test
   renders a CLI-saved response.
7. **`--path SCOPE`:** this is the address endpoint's supported `path` option (US
   scope, for example `/us/nj/camden`), passed straight to the SDK.
8. **`--max-records` cost:**
   - It needs an explicit `limit` in `--options`, so the cost is predictable.
   - Before the first request it prints the maximum request count, ceil(N / limit).
   - The cursor is the last feature's top-level `id`. The live spec says only "ID from a
     previous query exceeding the limit", so this is unverified until a live run.
   - When no cursor is present, paging stops and says so.
9. **Name shadowing:** the module path stays `regrid/offline/map.py` so the copied file
   name matches; the CLI imports it as `from regrid.offline import map as parcel_map`.

## Open risks

- Whether address responses include geometry by default is still unverified (the live
  check in Batch 1).
- `/verse` response size is unknown until called. The CLI cache handles any size; the
  skill avoids passing it through chat.
- Typeahead availability depends on the account's Enterprise status.
- Whether Cowork and the Claude apps support plugin commands and load the map's outside
  scripts and tiles.

## Left to the builder

- Exact CLI help text.
- Neighbour styling.
- CSV column order beyond the listed core columns.
- Cache file format.
- How `fields.json` is compacted.
- Windows CI matrix details.
