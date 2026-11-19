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

Single-result searches take `"limit":1`: `address`, `apn`, `owner` and `point` default to
5 records. `parcel` and `parcel-path` return one record and reject `limit`.
The CLI does not default premium or stacked flags to false; pass
`"return_stacked":false,"return_zoning":false,...` in `--options` as SKILL.md says,
unless the user requested them. This applies to `parcel` and `parcel-path` too, which
accept those flags but not `limit`.

Offline, no request: `regrid fields explain|search`, `regrid map`, `regrid export`.
Also: `regrid address-map ADDRESS OUT.html [--neighbours]` (one lookup, plus one
neighbours request when asked). Never run `report` or `client-token-typeahead`.

Paging: `--max-records N` on `point` (GET only), `area` and `query`, never `owner`.
It needs an explicit integer `limit` of at least 2 in `--options` and rejects a truthy `return_count`. It prints
`regrid: up to K requests for N records` before the first request; K is the enforced
worst case, allowing for a cursor that repeats the previous page's last record. It
never asks for more records than still needed (later pages may fetch, and bill, up to one extra record each) and outputs
`{"parcels": FeatureCollection, "pages": P, "complete": true|false}`. Get the user's agreed record budget first; page only within one task.

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
