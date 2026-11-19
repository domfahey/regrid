# Regrid CLI

## Executor

Use the CLI only in Claude Code, with `regrid` on PATH and `REGRID_TOKEN` already in
the environment. It is the full path for every lookup when MCP is unavailable, and
the only path for files (exports, tiles, saved maps). Inside the regrid repository,
load `.env` into the child process: `uv run --env-file .env --no-sync regrid ...`.
Rule: never read `.env`, print it, or echo the token. Output is JSON on stdout; the
request count is on stderr. Apply the same scope, limit and premium rules as over MCP.

## Command map

| Endpoint | Command |
| --- | --- |
| `/parcels/address` | `regrid address QUERY [--options '{"path":"/us/nj/camden"}']` |
| `/parcels/apn` | `regrid apn PARCELNUMB [--options '{"path":"/us/nj/camden"}']` |
| `/parcels/owner` | `regrid owner OWNER [--options '{"path":"/us/nj/camden"}']` (no `--max-records`) |
| `/parcels/point` | `regrid point --lat L --lon L [--options '{"radius":M}']` (or `--geojson` Point JSON or @FILE; `--method GET|POST`) |
| `/parcels/area` | `regrid area --geojson @FILE` (GeoJSON as a JSON string or @file) |
| `/parcels/query` | `regrid query --fields '{"field":{"op":v}}'` |
| `/parcels/{ll_uuid}` | `regrid parcel LL_UUID` |
| `/parcels/path` | `regrid parcel-path PATH` |
| `/parcels/typeahead` | `regrid typeahead QUERY` (Enterprise) |
| `/verse` | `regrid freshness --path /us/<st>/<county>` |
| `/schemas/parcel`, `/schemas/building`, `/schemas/address`, `/schemas/enhanced_ownership`, `/schemas/zoning` | `regrid schema NAME` |
| `/usage/detailed` | `regrid usage --detailed` |
| `/usage` | `regrid usage` |

Offline, no request: `regrid fields explain|search`, `regrid map`, `regrid export`.
Also: `regrid address-map ADDRESS OUT.html [--neighbours]` (one lookup, plus one
neighbours request when asked). Never run `report` or `client-token-typeahead`.

Paging: `--max-records N` on `point` (GET only), `area` and `query`, never `owner`.
It needs an explicit `limit` in `--options`, prints `regrid: up to K requests for N
records` before the first request, and outputs `{"parcels": FeatureCollection,
"pages": P}`. Get the user's agreed record budget first; page only within one task.

Export from a saved response, with no requests:
`regrid export RESPONSE [--csv F] [--geojson F] [--all-fields] [--replace]`. CSV cells
starting with `=`, `+`, `-`, `@`, tab or CR get a `'` prefix; plain numbers such as
`-75.1` stay as they are.

## Tiles

`regrid tilejson`, `regrid tile` and `regrid grid` are CLI-only: there is no MCP
equivalent. Tile output is binary or UTFGrid data for files; never put it in the map
page and keep it out of chat. `tile` requires `--output FILE`. Each call is one request: reserve it as a diagnostic.

## County pull dates (freshness)

`ll_last_refresh` on each parcel stays the default freshness answer over MCP. County
pull dates are not available over MCP; say they need the CLI. Report dates only and
never label data stale.

If the user supplies a saved `/verse` response file, run
`python3 <skill>/scripts/freshness.py county VERSE.json --path /us/<st>/<county>`
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

Every CLI command that calls the API ends stderr with `regrid: requests made: N`. The CLI
is ledger-unaware: reserve before the command and complete from that line, as
[batch and resume](batch.md#cli-and-suggestion-requests) describes.
