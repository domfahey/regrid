# Regrid CLI

## Contents

- [Executor](#executor)
- [Command map](#command-map)
- [Flags not in the map](#flags-not-in-the-map)
- [Tiles](#tiles)
- [County pull dates (freshness)](#county-pull-dates-freshness)
- [Ledger](#ledger)

## Executor

Use the CLI only in Claude Code, with `regrid` on PATH and `REGRID_TOKEN` already in
the environment. It is the full path for every lookup when MCP is unavailable, and
the CLI-only path for tiles and live county freshness (`regrid freshness`); saved
maps and exports can also be produced offline with `map.py` from saved MCP
responses. Inside the regrid repository,
load `.env` into the child process: `uv run --env-file .env --no-sync regrid ...`.
Rule: never read `.env`, print it, or echo the token. Output is JSON on stdout; the
request count is on stderr. Apply the same scope, limit and premium rules as over MCP.

## Command map

| Endpoint | Command |
| --- | --- |
| `/parcels/address` | `regrid address QUERY [--options '{"limit":1,"path":"/us/nj/camden"}']` |
| `/parcels/apn` | `regrid apn PARCELNUMB [--options '{"limit":1,"path":"/us/nj/camden"}']` |
| `/parcels/owner` | `regrid owner OWNER [--options '{"limit":1,"path":"/us/nj/camden"}']` (no `--max-records`) |
| `/parcels/point` | `regrid point --lat L --lon L [--options '{"limit":1,"radius":M}']` (or `--geojson` Point JSON or @FILE; `--method GET|POST`) |
| `/parcels/area` | `regrid area --geojson @FILE` (GeoJSON as a JSON string or @file) |
| `/parcels/query` | `regrid query --fields '{"field":{"op":v}}'` |
| `/parcels/{ll_uuid}` | `regrid parcel LL_UUID` |
| `/parcels/path` | `regrid parcel-path PATH` |
| `/parcels/typeahead` | `regrid typeahead QUERY` (Enterprise) |
| `/verse` | `regrid freshness --path /us/<st>/<county>` |
| `/schemas/parcel`, `/schemas/building`, `/schemas/address`, `/schemas/enhanced_ownership`, `/schemas/zoning` | `regrid schema NAME` |
| `/usage/detailed` | `regrid usage --detailed` |
| `/usage` | `regrid usage` |

Single-result searches take `"limit":1`: `address` defaults to 1 record, while `apn`,
`owner`, `point`, `area` and `query` default to 5. `parcel` and `parcel-path` return one record and reject `limit`.
The CLI/SDK sets `return_parcels=true` automatically on parcel endpoints, while stacked
and premium flags are not defaulted to false; pass
`"return_stacked":false,"return_zoning":false,...` in `--options` as SKILL.md says,
unless the user requested them. This applies to `parcel` and `parcel-path` too, which
accept those flags but not `limit`.

Offline, no request: `regrid fields explain|search` (subcommands `explain`, `search`), `regrid map`, `regrid export`.
Also: `regrid address-map ADDRESS OUT.html [--neighbours]` (one lookup, plus one
neighbours request when asked). Never run `report` or `client-token-typeahead`.

Paging: `--max-records N` on `point` (GET only), `area` and `query`, never `owner`.
It needs an explicit positive integer `limit` in `--options`, rejects a truthy `return_count`,
and rejects `offset_id` in `--options` (the CLI manages the cursor). It prints
`regrid: up to K requests for N records` before the first request; K = ceil(N / limit)
is the enforced worst case. It starts at `offset_id=0` so results come in id order
(rationale in [mcp-tools.md](mcp-tools.md#choosing-the-endpoint)). The cursor is exclusive,
so each page starts after the previous one, and it never
asks for more records than still needed. If numeric feature ids are not ascending past the
cursor (non-numeric ids are skipped by the check) it stops with `complete: false` and
`regrid: paging stopped: results not in cursor order`; it also stops when a page has no usable
cursor or only repeats (`no cursor in response`, `cursor did not advance`). It outputs
`{"parcels": FeatureCollection, "pages": P, "complete": true|false}`. Get the user's agreed record budget first; page only within one task.

Export from a saved response, with no requests:
`regrid export RESPONSE [--csv F] [--geojson F] [--all-fields] [--replace]`. CSV cells
starting with `=`, `+`, `-`, `@`, tab or CR get a `'` prefix; plain numbers such as
`-75.1` stay as they are.

## Flags not in the map

Global, before the command: `--timeout SECONDS`, `--base-url URL`, `--tiles-base-url URL`
(defaults: 30 s, `https://app.regrid.com/api/v2`, `https://tiles.regrid.com`; do not
point them at another host).
`--options`, `--fields` and `--metadata` take a JSON string or `@file`. `--geojson` is the
same JSON input on `point` and `area`, but on `export` it is an output file path.
Endpoint commands also take `--country us|ca` (default `us`; Canada stays as legacy,
out of this skill's scope):
Commands accepting `--country`: `point`, `area`, `address`, `apn`, `owner`, `query`, `parcel`, `parcel-path`, `typeahead`, `verse`, `usage`.
`--options` takes JSON; each command rejects keys it does not support:
- `--options` on `address`, `apn`, `owner`: `limit`, `path`, plus return flags.
- `--options` on `point` and `area`: `limit`, `radius`, `offset_id`, `return_count`,
  `return_geometry`, `return_custom_id`, plus return flags (`point --method POST` omits
  `offset_id` and `return_geometry`).
- `--options` on `query`: `limit`, `path`, `geojson`, `radius`, `offset_id`,
  `return_count`, `return_geometry`, `return_custom_id`, plus return flags.
- `--options` on `parcel` and `parcel-path`: return flags only (`limit` is rejected).
- `--options` on `verse`: `return_geometry` only.
- `--options` on `usage`: `return_full_history`, `begin_date`, `end_date`, `return_by_token`,
  `return_by_this_token`.
- `--options` on `schema`: `premium_only` (parcel schema only). `typeahead` takes no `--options`.

- `area --method GET|POST`: `POST` sends the GeoJSON as a JSON body for geometry too
  large for a URL; same read-only search, same one request per page. See
  [mcp-tools](mcp-tools.md#large-geometry-post-search). `point --method POST` needs GeoJSON.
- `query --validate-fields`: check fields and operators against the offline US field
  catalog before any request.
- `query --allow-unknown-fields` only has an effect together with `--validate-fields`; it
  lets through fields absent from the catalog (fields it marks non-queryable still fail).
- Raw `regrid verse [--options '{"return_geometry":true}']` is one request returning the full
  payload. County pull dates go through `regrid freshness` (cached, dates only); use raw
  `verse` only when the user explicitly asks for the full payload.
- `usage --detailed --options '{"begin_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}'` and
  `schema --options '{"premium_only":true}'` (parcel schema only).
- `address-map ADDRESS OUT.html --path PATH`: county scope; `--save-response FILE`
  keeps the lookup JSON; `--neighbours` adds one neighbours request.
- `address-map ADDRESS OUT.html --retrieved-at ISO` sets the shown timestamp;
  `address-map ... --replace` allows overwriting the output.
- `map RESPONSE OUT.html` options: `map --feature N`, `map --all-candidates`,
  `map --retrieved-at ISO`, `map --neighbours FILE`, `map --replace`; see [map](map.md).
- `tilejson [--format mvt|png]`, `tile Z X Y --output FILE [--format mvt|png] [--retina] [--replace]`,
  `grid Z X Y [--metadata RASTER_TILEJSON]`. `--retina` gives `@2x` raster tiles and requires `--format png`.
- Never run: `report` (`--comment`, `--path`, `--ll-uuid`, `--details`, `--details-text`)
  and `client-token-typeahead` (`--exp`); the first files an external report and
  the second issues a token.

## Tiles

`regrid tilejson`, `regrid tile` and `regrid grid` are CLI-only: there is no MCP
equivalent. Tile output is binary or UTFGrid data for files; never put it in the map
page and keep it out of chat. `tile` requires `--output FILE`. `tilejson` and
`tile` make one request each; `grid` makes two requests unless `--metadata` is
supplied (one for raster TileJSON discovery plus one for the UTFGrid). Reserve
each request as a diagnostic.

## County pull dates (freshness)

`ll_last_refresh` on each parcel stays the default freshness answer over MCP—report it
strictly as that parcel's refresh date, never as the whole county's freshness. County
pull dates are not available over MCP; say they need the CLI (`regrid freshness`, or
`freshness.py` on a supplied `/verse` file). Report dates only and never label data stale.

If the user supplies a saved `/verse` response file, run
`python3 "<skill>/scripts/freshness.py" county VERSE.json --path /us/<st>/<county>`
offline (no request). Over MCP never call `/verse`.

```
regrid freshness --path /us/<st>/<county> [--cache FILE] [--refresh] [--max-age-days N]
```

stdout is JSON: `path`, `county`, `state`, `last_refresh`, `assessor_data_date`,
`usps_data_date`, `verse_retrieved_at`, `cache` (`hit` or `miss`). The `/verse`
response is cached in `~/.cache/regrid/verse.json` (`%LOCALAPPDATA%\regrid\verse.json`
on Windows) and reused unless `--refresh` is given, no cache exists, the cache was
stored for a different `--base-url`, or it is older than 30 days (`--max-age-days N`
changes the limit); an old cache is refetched automatically with one request and a
stderr note.

## Ledger

Every CLI command that calls the API prints `regrid: requests made: N` on stderr. It is the last
line, except that `address-map` and `freshness` print it before their final note or error lines. The CLI
is ledger-unaware: reserve before the command and complete from that line, as
[batch and resume](batch.md#cli-and-suggestion-requests) describes.
