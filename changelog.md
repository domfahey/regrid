# Changelog

User-visible changes are grouped by release using the categories from [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Version numbering follows [Semantic Versioning](https://semver.org/); the current `0.x` API remains under development.

The Python SDK/CLI and the Regrid Research plugin are versioned independently. The latest tagged releases are SDK `0.4.3` (`sdk-v0.4.3`) and Regrid Research `0.9.3` (`regrid-research-v0.9.3`); the first were SDK `0.3.0` and Regrid Research `0.8.0`. Keep pending changes under Unreleased until the next release is prepared.

## Unreleased

### Fixed

- `--max-records` paging now starts at `offset_id=0` (verified live: point and area return a spatially ordered first page without `offset_id`, which could repeat records and skip ids below the cursor); it stops with `complete: false` and `regrid: paging stopped: results not in cursor order` if a page is not ascending past the cursor. `make live-full` checks the same ordering.

### Added

- `make live-full`: an opt-in, bounded (about 26 requests, hard cap 30) live check of every read-only endpoint that prints only aggregate PASS/FAIL/SKIP/NOTE lines.

## [SDK 0.4.3][sdk-v0.4.3] and [Regrid Research 0.9.3][regrid-research-v0.9.3] - 2026-11-19

Patch release with the fixes from the live checks (PR #21) and the 24-hour audit (PR #24), end-to-end coverage of every CLI subcommand (PR #22), higher-signal tests (PR #23) and skill drift guards (PRs #19, #20). Unverified at release:
- the Claude Code, Claude apps and Cowork map host checks (the map page passed a plain-browser render check)
- a live `/mcp` connection over the native HTTP transport
- model and Cowork acceptance evaluations
- whether POST geometry search accepts `return_parcels`

### Fixed

- Offline helpers: a path through a symlink loop gives a clean `Path contains a symlink loop` error in `map`, `export`, `address-map` (zero requests) and the skill's `map.py`, instead of a `RuntimeError` traceback. `render()`/`regrid map` refuse an output path that is a directory before rendering, like `export`. Exports fall back to `properties.fields.ll_uuid` when the top-level `ll_uuid` is an empty string, matching `feature_uuid`.
- `fields.py`/`regrid fields`: a custom `--catalog` too deeply nested to print gives the clean `fields:` error instead of a `RecursionError` traceback.
- CLI: the `--max-records` paging note about `pages`/`complete` keys in Regrid's response is computed from the final merged result, so it matches the output when those keys first appear on a later page.
- Evals: `_is_canadian_route` checks only route-bearing values (`url`, `path`, `endpoint`, and the tokens of shell `command`/`args`, including `--path=`), URL-decodes them, skips empty segments and flags `/schemas/ca`; free-text address fields such as `Los Angeles/CA/90001` are no longer flagged.
- Docs: `references/cli.md` says `address` defaults to 1 record (the other searches to 5); `references/mcp-tools.md` no longer says `fields.py` marks queryability (use `regrid query --validate-fields`) and notes that `return_parcels` on POST search is unverified.
- Changelog: the 0.4.2 `export` bullet no longer says the summary lists only core columns when no CSV is written; `columns` includes the extra fields whenever `--all-fields` is used.
- SDK: typed parcel validation accepts `ll_updated_at` timestamps with a space before a numeric offset (`2025-03-14 09:26:53 -0400`), the shape the live API returns. Before this, `ParcelFields`, `TypedRegridClient` and `make live` rejected real parcel responses.
- CLI: `--max-records` paging treats `offset_id` as exclusive, as verified live: later pages no longer request (and bill) one extra record, the printed worst case is `ceil(N / limit)` requests, and a page that adds no new records stops with `complete: false`.
- Skill: `references/batch.md` budgets `--max-records` paging as K = ceil(N / limit) requests and N records (it reserved N + (K - 1) records for the old extra-record behaviour).

### Verified

- Live, 2026-11-19: a default `/parcels/address` lookup includes the parcel `geometry` (a Polygon), and `offset_id` paging uses the feature `id` as an exclusive cursor with ascending ids across pages.

### Added

- Tests: the non-e2e suite's low-signal tests (bare `raises`, loose substrings, truthiness, tests asserting nothing) now assert exact messages, exact requests sent and negative outcomes (no request, no token, no file); each upgrade was mutation-tested.
- Tests: `make e2e` now runs every CLI subcommand end to end (subprocess or SDK over real local TLS against a fake Regrid server in `tests/e2e_support.py`): parcel searches incl. POST and `--max-records` paging, `TypedRegridClient`, `address-map`, `map`, `export`, `fields`, `freshness` caching, `schema`, `usage`, `verse`, tiles, `grid`, `report` and `client-token-typeahead` (local server only), plus redirect, error, timeout and missing-token safety. `tests/test_e2e_inventory.py` (in `make check`) fails if a subcommand has no e2e test.
- Tests: `tests/test_cli_docs.py` now fails unless `references/cli.md` shows every CLI subcommand as code (`regrid <cmd>` or a backtick before it) and every long option on one line that is word-bounded with that code subcommand (global options need only the flag). It checks presence, not accuracy.
- Tests: `tests/test_cli_docs.py` also checks the per-command `--options` keys listed in `references/cli.md` against the keys the client accepts (exact sets for `verse`, `usage` and `schema`; `parcel` and `parcel-path` reject `limit`). New `tests/test_mcp_docs.py` checks that the endpoint table in `references/mcp-tools.md` matches `references/endpoints.json` and that every API path it names is known or explicitly forbidden.

### Changed

- Docs: `references/cli.md` covers the remaining CLI flags (global `--timeout`, `--base-url`, `--tiles-base-url`, `--country`, `area --method`, `query --validate-fields` and `--allow-unknown-fields`, `address-map --path`, `--save-response` and `--retrieved-at`, tile `--format`, `--retina` and `--metadata`, `usage`/`schema --options`, `@file` values).
- Docs: `references/mcp-tools.md` adds recipes for `/parcels/query` operators, `/parcels/area` geometry, `/parcels/{ll_uuid}`, `/usage/detailed` dates and `/schemas` `premium_only`; POST geometry search on `/parcels/point` and `/parcels/area` for geometry too large for a URL; and the `return_field_labels`, `return_custom`, `return_custom_id` and `return_stacked` response options.
- CLI: `address`, `apn`, `owner`, `parcel`, `parcel-path`, `typeahead`, `client-token-typeahead`, `verse`, `usage` and `tilejson` now have descriptive `--help` text instead of their own name.
- Skill: `SKILL.md` is reworded to about 910 words (from 949) with the same rules, leaving room under the 950-word limit. `references/mcp-tools.md` folds the duplicate query-operator sentence into the query recipe.

## [SDK 0.4.2][sdk-v0.4.2] and [Regrid Research 0.9.2][regrid-research-v0.9.2] - 2026-11-19

Patch release with the fixes from the third audit (PR #17). Unverified at release:
- the live geometry check and a live `/mcp` connection over the native HTTP transport
- the Claude Code, Claude apps and Cowork map host checks (the map page passed a plain-browser render check)
- the live `offset_id` paging cursor
- model and Cowork acceptance evaluations

### Fixed

- Offline helpers: `export`, `map` and the paging sibling trim now read a parcel's `ll_uuid` from `properties.fields` when `properties.ll_uuid` is absent (new `regrid.offline.map.feature_uuid`), so exports keep the ID as Regrid gave it (any type), `--all-fields` no longer drops it and neighbour maps exclude the subject.
- `export --all-fields` now also adds the extra fields to GeoJSON properties, and the summary `columns` lists what was written.
- `export` refuses a directory as an output path before writing anything, even with `--replace`, reports NaN/Infinity in GeoJSON as a clean error.
- SDK: `validate_query` requires a boolean `paging` and checks a non-null `limit` against the client's `max_limit`, like `query`.
- CLI: `--max-records` paging rejects a `limit` above the client maximum before any request.
- `freshness` rejects booleans for `max_age_days`.

### Changed

- The property-research skill description now covers parcel field definitions and codes; the CLI reference states exactly where the `regrid: requests made: N` line appears.

## [SDK 0.4.1][sdk-v0.4.1] and [Regrid Research 0.9.1][regrid-research-v0.9.1] - 2026-11-19

Patch release with the fixes from the second 24-hour bug audit (PR #15). Unverified at release:
- the live geometry check and a live `/mcp` connection over the native HTTP transport
- the Claude Code, Claude apps and Cowork map host checks (the map page passed a plain-browser render check)
- the live `offset_id` paging cursor
- model and Cowork acceptance evaluations

### Fixed

- CLI and SDK:
  - Deeply nested JSON now fails with one sanitized error instead of a traceback: in the CLI (API responses, a freshness cache, `--options`/`--fields`/`--geojson`, followed by the usual `regrid: requests made: N` line), in the SDK request encoders and validators (`geojson=`, `fields=`; a `ValueError` with no chained input), and in the `fields.py` and `freshness.py` helpers.
  - `address-map`, `map` and `export` share one same-file check (`regrid.offline.map.same_file_key`: resolved path, Unicode NFC, case-folded), so names differing only by letter case or Unicode form are refused before any request or write.
  - Paging keeps a response's own `pages`/`complete` values as `response_pages`/`response_complete`, never overwrites a `response_pages`/`response_complete` already in the response (it prints a note instead), de-duplicates parcels with one id rule (ids that are unhashable are accepted, and `True`, `1` and `1.0` stay distinct).
- Offline helpers:
  - `map.py render` reports a missing output folder clearly. Rings under 0.01 square metres are degenerate: degenerate holes and member polygons are dropped with a "Degenerate ring skipped" warning, and a parcel fails with "Polygon ring has zero area" only when no usable polygon remains.
  - Freshness caches dated in the future are treated as stale.
  - The field catalog rejects entries without a string name.
- Packaging: the credential scan no longer flags words that merely contain `rg_`, and it now catches RSA, EC and OpenSSH private keys.
- Skill guidance:
  - Paged searches and refresh-by-path now use `authorized_retry=True`, and paged searches budget for one extra record per later page, matching the workflow helper.
  - Single-result search examples (address, apn, owner, point) pass `limit` 1, Regrid ID and path lookups need no limit, and the notes say the CLI doesn't turn paid datasets off by default.
- Evals: the Canadian-route check looks at path segments (including URL paths and `path=` values): a `ca` segment followed by more segments is flagged unless it follows `us`, and text such as `CA/ something` is not. A fixture now uses the real error message.

## [SDK 0.4.0][sdk-v0.4.0] and [Regrid Research 0.9.0][regrid-research-v0.9.0] - 2026-11-19

Unverified at release:
- the live geometry check and a live `/mcp` connection over the new native HTTP transport
- the Claude Code, Claude apps and Cowork map host checks (the map page passed a plain-browser render check)
- the live `offset_id` paging cursor
- model and Cowork acceptance evaluations

### Added

- Regrid Research plugin: archives now include the repository `LICENSE` (at the root of the plugin archives and inside the standalone skill folder), and `plugin.json` declares `license`, `repository` and `homepage`. No icon is set; one is needed only for directory submission.

- SDK: `RegridClient.validate_query(fields, *, paging=False, ...)` validates a query exactly as `query()` would without sending a request, and `QueryPagingError` (exported from `regrid`, a `ValueError`) marks filters that can't be paged with `offset_id`. `regrid.offline.map.write_atomic_bytes`, `regrid.offline.map.check_mappable` and `regrid.offline.freshness.check_max_age_days` are new public helpers.

- Regrid Research plugin: `PRIVACY.md` (the plugin collects, stores and sends no data of its own; lookups go to Regrid's MCP server under Regrid's privacy policy; map pages load Leaflet from unpkg.com and imagery from Esri) ships in both plugin archives, and `plugin.json` declares `privacyPolicyUrl`.

- Regrid Research plugin README: MCP server coverage summary (tools, endpoints, options, and deliberately unused features), linking to the skill references.

### Changed

- Regrid Research Claude Code package: the MCP config now uses Claude Code's native HTTP transport with an `x-regrid-token: ${REGRID_TOKEN}` header instead of an unpinned `npx -y mcp-remote` bridge. Security: the token no longer appears in process arguments, no npm package is downloaded, and Node.js is no longer required. The Cowork MCP config is unchanged.
- Regrid Research plugin README: "Validation and acceptance" now leads with the current 0.8.0 status, the builder allowlist lists every shipped file, and the 0.2.0 to 0.5.0 verification logs moved to a "Historical verification" section in `evals/README.md`. The map host checklist now names `results/map-hosts-0.8.0.json`.
- Regrid Research skills: both descriptions now state exclusions (property-research: Batch API jobs, data-issue reports, appraisals and legal ownership opinions; setup: not for lookups; non-US requests still load property-research, which states the US-only scope), every helper invocation uses one quoted `python3 "<skill>/scripts/<name>.py"` convention (also in the `address-map` command), `SKILL.md` tells agents not to open `fields.json`, and `evals/run.py packet` no longer inlines `fields.json` unless the packet contains feature cases (including `--suite all`).
- Regrid Research skills: richer trigger descriptions, a shorter `property-research` routing page with match/answer rules in `references/answers.md`, a single budget/ledger source in `batch.md`, and consistent "neighbour" and "premium dataset" terminology.

### Fixed

- Regrid Research docs: the plugin README now lists every endpoint that accepts premium dataset flags, `property-research` routes a user-supplied `/verse` file to `freshness.py` and pairs composition with the answers guide, and the evals README and feature rubric use current counts and terminology.

- Paging and `address-map` edge cases: trimmed-parcel sibling removal also follows `ll_uuids` lists (a building linked to a kept parcel is retained), duplicates within one incoming page are skipped, `address-map --neighbours` skips the neighbours request when the subject outline is invalid or the path is a string outside `/us/` (a non-string path no longer blocks it), and `QueryPagingError` no longer carries the underlying exception as context.

- `--max-records` paging:
  - Never requests more records than still needed.
  - Prints and enforces one honest worst-case request cap, including when the cursor repeats the previous page's last record.
  - Merges `buildings` and `zoning` collections from every page.
  - Stops cleanly (keeping fetched records) when a feature id isn't a usable cursor.
  - Rejects `return_count` and unsupported query filters before the first request.
  - De-duplicates ids within a page and de-duplicates repeated sibling features from an inclusive cursor.
  - Accepts ASCII-digit string cursor ids and `return_count: false`, requires `limit` of at least 2, and drops siblings of parcels trimmed to the record count.
  - Later pages may fetch (and bill) up to one extra record each.
- `address-map`:
  - Skips the neighbours request when the subject parcel isn't mappable (non-US path or no geometry).
  - Rejects directory targets before any request.
  - Saves responses atomically without following symlinks.
- `freshness`:
  - Rejects non-finite, negative or huge `--max-age-days` values up front.
  - Shares one cache across base URLs that differ only by a trailing slash.
- Map helper:
  - Fills page placeholders in one pass, so record text containing a placeholder name can't break the page.
  - Reports a non-finite area ratio as unavailable.
  - Guards CSV cells that start with non-ASCII digits.
  - Rejects NaN inside list/dict CSV cells.
- Discovery evaluations stage every reference file the plugin ships.

## [SDK 0.3.0][sdk-v0.3.0] and [Regrid Research 0.8.0][regrid-research-v0.8.0] - 2026-11-19

First tagged release of both components. It contains every change made before tagging, so earlier plugin versions (0.2.0–0.7.0) and SDK versions (0.1.0–0.2.0) appear as entries below rather than separate releases. Release assets:
- the wheel and source package (SDK)
- the Cowork, Claude Code and standalone-skill archives (plugin)

Unverified at release:
- the live geometry check
- the Claude Code, Claude apps and Cowork map host checks
- the live paging cursor
- model and Cowork acceptance evaluations

### Added

- Regrid Research 0.8.0 and SDK 0.3.0 ship batches 2-4 together on top of 0.7.0 / 0.2.0:
  - CLI commands:
    - `regrid fields explain|search` reads an offline catalog of the 169 US parcel fields.
    - `regrid freshness --path /us/<state>/<county>` reports county pull dates from `/verse`.
      It reports dates only and never labels data stale. It prints the stored
      `verse_retrieved_at`, not a computed cache age.
      - The response is cached atomically. The cache is refetched after 30 days
        (`--max-age-days N`) or when it was stored for another base URL.
    - `regrid export RESPONSE --csv/--geojson [--all-fields]` writes CSV and GeoJSON
      offline from a saved response.
    - `regrid address-map --neighbours` adds one point search (100 m, up to 25 records)
      and draws neighbouring outlines. If that search fails, the subject map still renders.
    - `regrid map --neighbours FILE` does the same from saved files.
  - `--max-records N` pages `point` (GET), `area` and `query` within a request cap:
    - It needs an explicit `limit`.
    - It keeps the first page's top-level keys and removes duplicate features by id.
    - It stops when a page adds nothing new.
    - It adds a `complete` flag, which is true only when results ended or N records were
      reached. A failure on page 2 or later prints the partial result with
      `complete: false` and exits 1.
  - SDK:
    - Public `RegridClient.request_count` counts requests actually sent.
    - New standard-library `regrid.offline` package (`map`, `fields`, `freshness`). It is
      the source of the skill's bundled helpers, which are kept byte-identical by
      `scripts/sync_skill_helpers.py`.
  - Skill: guidance for:
    - paid datasets (`premium.md`)
    - the bundled field catalog (`fields.py`, `fields.json`)
    - refresh by Regrid path, and address suggestions (typeahead, then path; Enterprise only)
    - opt-in neighbours with request-budget accounting
    - export, count before pulling, and paging
    - a full CLI path for Claude Code (`references/cli.md`)

    `endpoints.json` adds `/parcels/path`, `/parcels/typeahead`, `/verse`, `/schemas/*`
    and `/usage/detailed`.
  - A Windows CI job runs the offline helper tests and the offline/freshness CLI tests, and it passes.
  - Verification:
    - The map page passed a render check in a plain browser (Chromium via Playwright, synthetic
      data; `evals/results/map-hosts-0.8.0.json`). This is not a check inside a Claude host.
    - Not run:
      - the live geometry check
      - the Claude Code, Claude apps and Cowork map host checks
      - the live paging cursor (the `offset_id` cursor field is unverified against the live API)
      - model and Cowork acceptance evaluations
- SDK 0.2.0: `regrid map RESPONSE OUTPUT` renders a saved US parcel response as a satellite map page offline, and `regrid address-map ADDRESS OUTPUT` makes one address request, saves the response beside the page (`OUTPUT` with a `.json` suffix, or `--save-response`) and renders it. `address-map` reports `regrid: requests made: N` on stderr. `make live` now also reports whether the parcel geometry was present, null or absent. The live geometry check has not been run (awaiting user: not run).

- Regrid Research 0.7.0 adds the `/regrid-research:address-map` command (Claude Code and Cowork archives only): one address request, the response saved verbatim, rendered with `scripts/map.py`, summarised and presented per the map guide. No neighbouring parcels. Host checks in Claude Code, the Claude apps and Cowork are recorded in `evals/results/map-hosts-0.7.0.json` and are all not run (awaiting user). The SDK is `0.2.0`.

- Regrid Research 0.6.0 adds `scripts/map.py`, a stdlib-only offline helper that renders a saved US parcel response as an interactive Esri satellite map, with boundary validation and a recorded-area cross-check. It refuses parcels whose Regrid path is outside `/us/`, accepts GeoJSON altitude values, handles boundaries that cross 180°, never overwrites an existing page without `--replace`, and leaves the process umask unchanged. The map guide asks for `return_geometry=true` where supported and distinguishes a missing boundary (`null`) from geometry that was not requested. The map guide and packaging cover all three archives; the page loads Leaflet and imagery in the viewer's browser.

- MIT license, public contribution/security/conduct guides, issue and PR templates, pinned GitHub Actions CI, and dependency-update configuration.

- Claude Regrid Research plugin with a bounded property-research skill, setup diagnostics, and a token-free MCP bridge configuration; includes import instructions and acceptance checks.

- `make doctor` checks local `.env` presence and token configuration without revealing credentials or making API calls. Both `make doctor` and `make live` explicitly load `.env` through uv.

- Synchronous SDK and CLI covering all 33 operations in the supplied US/Canada OpenAPI contract, including public schemas, usage, reports, and temporary typeahead tokens.
- TileJSON, raster/vector and retina tile downloads, and UTFGrid retrieval through advertised metadata, with metadata reuse and same-origin enforcement.
- Opt-in `TypedRegridClient` with complete documented response structures and addon properties, lossless serialization, and shared `.raw` dictionary access.
- Versioned catalog of 169 US parcel fields with SQL types, tiers, coverage-column names, and selected verified queryability, source, standardization, and preferred-field metadata.
- Generated `ParcelFields` and opt-in `ParcelProperties.typed_fields`, preserving existing dictionary access, identifiers, unknown fields, and omitted/null distinctions.
- Optional SDK/CLI query validation with an explicit escape hatch for unknown fields; existing queries keep their default behavior.
- Opt-in `make live` smoke test: one-record lookup, premium datasets disabled, validation of the same response, before/after usage checks, and redacted output. Defaults to `24 pennbrook dr haddonfield nj 08033`; `REGRID_LIVE_ADDRESS` optionally overrides it.
- Development commands for installation, lint, formatting, typing, coverage-gated mocked tests, and separate local HTTPS E2E tests.
- Contributor, architecture, API coverage, parcel interpretation, and UTFGrid documentation; placeholder-only `.env.sample`.

### Changed

- SDK 0.3.0: every CLI command that calls the API now ends stderr with `regrid: requests made: N`; `address-map` and `freshness` print it before their error lines. Stdout JSON is unchanged, but tools that compare stderr exactly will see the new line.
- The coverage gate for `make test` and `make check` rises from 90% to 95% (`pyproject.toml` and the Makefile).
- CI uses `actions/checkout` 7.0.1 and `actions/setup-python` 7.1.0, pinned by commit.

- Regrid Research 0.8.0 reverses the satellite-map design's non-goal of GIS export files, by owner decision: `map.py export` and `regrid export` write CSV and GeoJSON from a saved response.

- Regrid Research 0.6.0 adds satellite parcel maps (see Added); request budget and handoff schemas are unchanged.

- Regrid Research 0.5.2 re-audits the MCP references against the live server (Regrid Support 2.3.1, November 18, 2026): all seven tools are documented with their role and request accounting; spec titles, including the setup usage example, carry the ` (reference)` suffix; `fetch` uses `project/section/slug` IDs, an optional `format`, and reports unknown IDs without `isError`; `endpoints.json` now covers the APN, owner, point, area, query, and Regrid ID endpoints the skill advertises, in addition to address and usage, and notes that parcel queries require a field filter. It also states US-only scope and tightens workflow-helper and eval-runner validation (see Fixed). Saved evaluation reports predate these reference changes. Handoff schemas are unchanged.

- Regrid Research 0.5.1 is a fix-only version: strict boolean checkpoint/retry flags in the workflow helper and corrected authentication detection in the discovery runner (see Fixed). Handoff schemas are unchanged. Detection was checked against a logged-out Claude CLI 2.1.327, which records the first trial as blocked; an expired OAuth session was not reproduced.

- Regrid Research 0.5.0 adds opt-in `1.1` query handoffs and explicit upgrades while retaining `1.0` compatibility; caller-verified per-attempt reconciliation preserves uncertain history. Setup diagnostic calls share the workflow request budget without consuming property records. Evidence-only prose avoids loading schemas/examples, and saved tool catalogs load only for unavailable or mismatched live schemas. New regression scenarios cover these composition boundaries; offline evaluations remain separate from Claude/Cowork acceptance.

- Regrid Research 0.4.0 adds metadata-first discovery trials with without-skill baselines and trace/model recording, direct resource links, qualified MCP names, safer actionable validation diagnostics, and an explicit checkpoint save CLI. The helper requires Python 3.10+ with only the standard library; `workflow.py save INPUT DEST` validates before saving and refuses existing destinations unless an explicitly requested update uses `--replace`. The [0.4.0 acceptance report](plugins/regrid-research/evals/results/authoring-0.4.0-report.json) records Claude model evaluations blocked by expired CLI authentication and Cowork import/authenticated lookup unverified because Desktop inspection was unavailable. Passing local tests and structural validation does not establish those acceptance gates.

- Regrid Research 0.3.0 adds composable structured results with independent lookup/match statuses, shared request/record budgets, supplied-evidence provenance, flexible presentation, and explicitly requested checkpoint/resume helpers. Adds downstream handoff evaluations and includes the offline helper in all package variants.

- Regrid Research 0.2.0 separates Cowork HTTP and Claude Code local-bridge packages while sharing one canonical skill and its live MCP references. Adds explicit match states, unit/multiple-parcel handling, finite-list budgets, conditional ownership answers, response reuse, reproducible packaging checks, and offline behavioral evaluations.

- Clarify Cowork web-connector authentication: limited request-header beta, custom-header approval, standalone skill setup, and separation from Desktop Developer JSON and the local Claude Code bridge.

- Adopt Pydantic v2 for strict endpoint-specific requests and optional response validation, retaining raw SDK dictionaries and CLI JSON output.
- Replace weak test assertions with exact SDK/CLI wire contracts, binary-output checks, and meaningful validation regressions. Generated parcel models are checked for drift during tests.
- Expand `.gitignore` for Python build/test artifacts, local research output, editor files, and macOS metadata while retaining `.env.sample`.

### Fixed

- Reject `ll_updated_at` timestamps whose time-zone offset minutes are 60–99 (previously accepted and silently normalized).
- Regrid Research workflow helper: `reserve_attempt` rejects non-list or non-string input IDs instead of splitting a string into characters; `set_result` raises `ValidationError` for non-object rows and unknown input IDs; `reconcile_attempt` runs the validator's reconciliation checks before adjusting budget counters, so it reports the actual reason (for example "Only uncertain attempts can be reconciled") instead of a misleading budget-counter error. `ValidationError` remains a `ValueError` subclass.
- Discovery eval runners ignore blank stream-JSON lines and tolerate explicit nulls in `message`, `content`, `name`, and `input` instead of failing or crashing; non-object tool inputs are kept as recorded rather than replaced with `{}`.
- Restrict automatic parcel-search limits to parcel routes so public address-schema requests receive no search parameters.
- Reject non-finite upstream JSON numbers before serialization can silently convert them to null.
- `TypedRegridClient.grid()` accepts the `TileJSON` model returned by `TypedRegridClient.tilejson()` as `metadata`.
- `query(..., country="US", validate_fields=True)` no longer fails; country case is normalized before catalog validation.
- `ll_updated_at` validation behaves the same on Python 3.10 as on later versions and accepts lowercase `t`/`z`, any fractional-second precision, and `+HH`/`+HHMM` offsets. Only the extended form `YYYY-MM-DD`, `T` or space, `HH:MM:SS`, optional fraction, then `Z` or an hour/minute offset is accepted; basic-format, week-date, seconds-less, and offset-with-seconds timestamps that newer Python versions parsed are rejected.
- The CLI treats an empty or whitespace-only `REGRID_TOKEN` as unset, so public commands work and authenticated commands report the missing-token error. Surrounding whitespace is trimmed from the token.
- UTFGrid discovery falls back to `grids` when TileJSON contains `"grid": null`.
- Reject a `lat` or `lon` supplied without the other on point searches, including when GeoJSON is given, and whitespace-only `path` options on address, APN, owner, and query searches.
- Reject service URLs containing `?`, `#`, whitespace, or userinfo delimiters, which previously moved endpoint paths into the query string or fragment.
- Regrid Research workflow helper requires real booleans for `requested`, `replace`, and `authorized_retry`; truthy non-boolean values such as `"false"` no longer write or replace checkpoints or authorize retries.
- The discovery evaluation runner no longer marks a completed trial as blocked when its output merely mentions an authentication phrase; authentication failures are detected from stderr and error events only.

### Security

- CSV export prefixes `'` to cells, including the header, that start with `=`, `+`, `-`, `@`, tab or carriage return, so spreadsheets don't run them as formulas. Plain numbers such as `-75.03` are left unchanged.
- The `/verse` cache is written atomically to a private directory and never stores the token or request URLs. The cache-write warning omits the path.
- `regrid map`, `map.py render` and `export` refuse to write over their own input files, so a saved paid response can't be destroyed. Export checks every target before writing anything.
- Record text from neighbouring parcels is escaped in the map page, the same way as the subject parcel's.
- Store account tokens as `SecretStr` and mask temporary-token models unless explicitly exported.
- Sanitize request and response-validation failures without retaining input-bearing Pydantic exceptions.
- Transport, JSON-decode, and JSON/GeoJSON input errors, including CLI JSON arguments, no longer retain the original exception as `__context__`, which could hold a token-bearing URL, the response body, or raw input.
- Reject unsafe UTFGrid URLs and replace metadata credentials with the configured client token.
- Keep local environment files and private keys out of Git. The live runner suppresses HTTP logging and prints no credentials, property details, response bodies, or exception text.

## Release Maintenance

SDK/CLI and plugin versions are independent. At release time, move only the relevant pending entries into a component-specific version heading dated `YYYY-MM-DD`; retain other pending work under Unreleased.

- For an SDK/CLI release, synchronize `pyproject.toml` and `src/regrid/__init__.py`.
- For a plugin release, update `plugins/regrid-research/.claude-plugin/plugin.json` and the documented archive names. Run `.venv/bin/python scripts/build_claude_plugins.py` to rebuild the Cowork, Claude Code, and standalone skill ZIPs in ignored `dist/`; all three archive versions derive from the plugin manifest. Validate the rebuilt artifacts and record model/Cowork acceptance separately from structural checks.

Describe user-facing changes rather than copying commit logs. Add repository comparison links when a remote and release tags exist; do not invent release dates or links.

[sdk-v0.3.0]: https://github.com/domfahey/regrid/releases/tag/sdk-v0.3.0
[regrid-research-v0.8.0]: https://github.com/domfahey/regrid/releases/tag/regrid-research-v0.8.0
[sdk-v0.4.0]: https://github.com/domfahey/regrid/releases/tag/sdk-v0.4.0
[regrid-research-v0.9.0]: https://github.com/domfahey/regrid/releases/tag/regrid-research-v0.9.0
[sdk-v0.4.1]: https://github.com/domfahey/regrid/releases/tag/sdk-v0.4.1
[regrid-research-v0.9.1]: https://github.com/domfahey/regrid/releases/tag/regrid-research-v0.9.1
[sdk-v0.4.3]: https://github.com/domfahey/regrid/releases/tag/sdk-v0.4.3
[regrid-research-v0.9.3]: https://github.com/domfahey/regrid/releases/tag/regrid-research-v0.9.3
[sdk-v0.4.2]: https://github.com/domfahey/regrid/releases/tag/sdk-v0.4.2
[regrid-research-v0.9.2]: https://github.com/domfahey/regrid/releases/tag/regrid-research-v0.9.2
