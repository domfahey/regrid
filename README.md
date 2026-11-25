# Regrid SDK

A synchronous Python SDK and command-line client for the [Regrid](https://regrid.com/) Parcel and Tileserver APIs, built on HTTPX and Pydantic v2. `RegridClient` keeps dictionary responses for compatibility; `TypedRegridClient` validates responses into models. Both validate request parameters strictly. Tile requests return bytes.

## Scope

This project targets **United States** parcel data. US endpoints are the only ones
prioritized for development, verification, and the Claude plugin. Canadian
(`country="ca"`) routes from the supplied contract remain implemented and tested
but receive no further feature work. Regrid's Global (international) and Batch
Processing APIs are out of scope and not implemented.

## Documentation

- [Repository guidelines](AGENTS.md): module layout, coding conventions, test gates, and plugin workflow.
- [Architecture](architecture.md): components, request flow, validation boundaries, and extension points.
- [Contributing](CONTRIBUTING.md): setup, tests, and pull request workflow.
- [Security policy](SECURITY.md) and [code of conduct](CODE_OF_CONDUCT.md).
- [Changelog](changelog.md): user-visible changes and release status.
- [API reference](REFERENCE.md): the supplied Regrid API documentation summary.
- [Operation coverage](docs/api-coverage.md): all 33 supplied OpenAPI operations and parameter profiles.
- [Parcel schema guidance](docs/parcel-schema-guidance.md): field meanings, standardized alternatives, and coverage limitations.
- [Response models](docs/model-coverage.md) and [UTFGrid](docs/utfgrid.md): typed fields and tileserver discovery.
- [Todos](todos.md): remaining open items and out-of-scope decisions.

## Installation

Requires Python 3.10 or later, Git, Make, and [uv](https://docs.astral.sh/uv/).
Clone the source and try the CLI without credentials or API calls:

```sh
git clone https://github.com/domfahey/regrid.git
cd regrid
make install
.venv/bin/regrid --help
```

The editable installation provides `.venv/bin/regrid`. Activate `.venv` to use
`regrid` directly, or run `uv run regrid`. Public schema commands do not require
a token. Development dependencies resolve locally; `uv.lock` is not tracked.
The SDK is not published to PyPI; prebuilt wheels are attached to
[GitHub Releases](https://github.com/domfahey/regrid/releases) (for example,
`pip install regrid_sdk-0.5.0-py3-none-any.whl`).

### Optional authenticated setup

Only configure a token when calling authenticated Regrid endpoints. Create `.env`
from `.env.sample` if it does not already exist, then edit it privately:

```sh
# First-time setup only; do not overwrite an existing .env.
cp -n .env.sample .env
# Edit .env locally, then check configuration without contacting Regrid.
make doctor
# Explicit authenticated usage request; does not retrieve parcels.
uv run --env-file .env --no-sync regrid usage
```

The SDK and CLI do not automatically load `.env`. Use `uv run --env-file .env`
for authenticated commands or SDK scripts; it loads credentials into the child
process. Keep tokens in local configuration or a secret manager. `.env` and
`.env.*` are ignored; `.env.sample` is placeholder-only. Never commit credentials,
private keys, or populated environment files. Later direct CLI/Python examples
assume `REGRID_TOKEN` is already available in their process environment.

To add a source checkout to another uv project:

```sh
uv add /absolute/path/to/regrid
```

## Development commands

| Command | Purpose |
| --- | --- |
| `make install` | Install the editable SDK, CLI, and development tools with uv |
| `make lint` | Run Ruff lint checks |
| `make format` | Format source and tests |
| `make format-check` | Verify formatting without editing files |
| `make typecheck` or `make type` | Run mypy on the SDK and CLI |
| `make test` | Run mocked tests and require at least 95% combined line and branch coverage |
| `make doctor` | Check `.env` presence and a nonblank, non-placeholder effective token locally; no API calls |
| `make live` | Explicit bounded live Regrid smoke test; requires token; uses the default test address |
| `make live-full` | Explicit live check of every read-only endpoint (about 26 requests, hard cap 30); requires token |
| `make e2e` | Run subprocess and real local HTTPS tests |
| `make check` | Run lint, format-check, typecheck, and the coverage-gated mocked suite |
| `uv build` | Build wheel and allowlisted source archives into `dist/` |
| `.venv/bin/python scripts/build_claude_plugins.py` | Build the Cowork, Claude Code, and standalone skill ZIPs into `dist/` |
| `.venv/bin/python scripts/sync_skill_helpers.py [--check]` | Copy `src/regrid/offline/*.py` into the skill's `scripts/` (byte-identical); `--check` fails on drift |
| `.venv/bin/python scripts/generate_parcel_fields.py [--check]` | Regenerate `src/regrid/parcel_fields.py` from `src/regrid/data/parcel_fields.json` |
| `.venv/bin/python scripts/generate_skill_fields.py [--check]` | Regenerate the skill's compact `references/fields.json` from the packaged field catalog |

Coverage includes every SDK and CLI module; XML output is written to ignored `coverage.xml`. E2E tests are separate from `make check`: they require `openssl` and permission to bind a localhost port, generate temporary TLS keys, and verify TLS using a temporary trusted certificate. They do not contact Regrid or incur API charges. Run `make check && make e2e` for the full offline suite. `make live` is a separate, explicitly invoked service check that can incur a parcel charge. Override `PYTHON` if using a virtual environment other than `.venv`.

## Command line

```sh
.venv/bin/regrid --help
.venv/bin/regrid schema parcel
.venv/bin/regrid address "123 Main St, Dallas, TX" --options '{"limit":1,"path":"/us/tx/dallas"}'
.venv/bin/regrid apn "0012340000" --options '{"path":"/us/tx/dallas"}'
.venv/bin/regrid point --lat 32.7767 --lon -96.7970 --options '{"radius":10,"limit":5}'
.venv/bin/regrid query --validate-fields --fields '{"geoid":{"eq":"48113"}}' --options '{"limit":5}'
.venv/bin/regrid area --method POST --geojson @area.geojson --options '{"limit":5}'
.venv/bin/regrid parcel-path /us/nj/camden/haddonfield/123 --options '{"return_parcels":true}'   # refresh a saved result by path
.venv/bin/regrid usage --detailed
.venv/bin/regrid tilejson --format mvt
.venv/bin/regrid grid 15 8828 12121
.venv/bin/regrid tile 15 8828 12121 --format png --retina --output parcel.png [--replace]
.venv/bin/regrid map response.json parcel.html          # offline satellite map of a saved response
.venv/bin/regrid address-map "123 Main St, Dallas, TX" parcel.html   # one request, saves parcel.json
.venv/bin/regrid address-map "123 Main St, Dallas, TX" parcel.html --neighbours   # opt-in: one extra request, up to 25 records
.venv/bin/regrid point --lat 32.7767 --lon -96.7970 --options '{"limit":100}' --max-records 300   # bounded paging
.venv/bin/regrid point --lat 32.7767 --lon -96.7970 --options '{"return_count":true}'   # count matches before pulling
.venv/bin/regrid fields search owner          # offline field catalog, no request
.venv/bin/regrid fields explain usedesc
.venv/bin/regrid freshness --path /us/nj/camden   # county data dates from a cached /verse response (refetched after 30 days; --max-age-days N)
.venv/bin/regrid export parcel.json --csv parcel.csv --geojson parcel.geojson   # offline export
```

Every API command prints `regrid: requests made: N` to stderr (JSON on stdout is unchanged); SDK users can read `RegridClient.request_count`. `--max-records N` on `point`, `area` and `query` follows `offset_id` cursors for up to N records and requires a positive integer `limit` in `--options`. Output is the first page's response with `parcels.features` replaced by the merged, de-duplicated features (other list-valued keys and FeatureCollection keys are merged; a key first seen on a later page is added, and a key whose shape changes keeps page 1's value with a `regrid: paging note` on stderr), plus `pages` and `complete`. A truthy `return_count` is rejected with `--max-records`. Paging starts at `offset_id=0`: verified live, point and area return their first page in spatial order without an `offset_id` but in ascending id order with one, so starting at 0 gives id-ordered pages with no gaps. The `offset_id` cursor is exclusive (verified live), so each page starts after the previous one and requests at most the remaining records; the printed cap is `ceil(N / limit)`: 300 records at `limit` 100 prints `up to 3 requests`. If a server repeats the cursor record anyway, repeats are de-duplicated in every merged collection, and sibling features of parcels trimmed to N (matched by `properties.ll_uuid`) are dropped. A cursor id may be a non-negative integer or a string of ASCII digits. `complete` is true only when results ended (a short page) or N records were reached; it is false if paging stops for any other reason. If a later page fails or is malformed, the partial result is printed with `"complete": false` and the command exits 1. Paging also stops with `complete: false` and `regrid: paging stopped: results not in cursor order` if a page's numeric feature ids are not strictly ascending or not all above the previous cursor (non-numeric ids are skipped by this check), so records are never skipped silently. It also stops with `complete: false` if a page has no usable cursor (`regrid: paging stopped: no cursor in response`) or adds only already-seen records (`regrid: paging stopped: cursor did not advance`). `address-map --neighbours` draws neighbouring outlines within 100 m, capped at 25 records. `regrid export RESPONSE` writes core columns to CSV and GeoJSON properties (`--all-fields` appends the rest to both; IDs are exported as given) and never overwrites without `--replace`.

`regrid map RESPONSE OUTPUT [--feature N] [--all-candidates] [--retrieved-at ISO] [--neighbours FILE] [--replace]` renders offline with no request (the output may not be the response or neighbours file). `regrid freshness` reuses its `/verse` cache for 30 days (`--max-age-days N`) and only for the same `--base-url`; an older cache is refetched with one request and a stderr note. `regrid address-map ADDRESS OUTPUT [--path SCOPE] [--save-response FILE] [--retrieved-at ISO] [--neighbours] [--replace]` makes one address request (up to two requests with `--neighbours`), saves the response next to the page unless `--save-response` is given, and—like `regrid freshness`—prints `regrid: requests made: N` to stderr before its note or error lines (unlike other API commands, where it is the last stderr line). Pages load Leaflet and Esri imagery in the viewer's browser.

Every API endpoint method has a CLI command: `point`, `area`, `address`, `apn`, `owner`, `query`, `parcel`, `parcel-path`, `typeahead`, `client-token-typeahead`, `schema`, `verse`, `usage`, `report`, `tilejson`, `tile`, and `grid`. Workflow commands build on them: `address-map` and `freshness` make API requests, while `map`, `export` and `fields` run offline with no token or client. The offline helpers live in the standard-library-only `regrid.offline` package (`map`, `fields`, `freshness`), which is also the source of the plugin's bundled scripts. Use `<command> --help` for arguments. `python -m regrid` is equivalent to the installed command.

Use `--country ca` where Canadian endpoints are supported. `--options` accepts an object or `@file` containing JSON for supported SDK keyword parameters. `--fields` and `--geojson` also accept JSON or `@file`. Report details accept structured `--details` or plain `--details-text`; `report` submits an external data issue. The `client-token-typeahead` command intentionally prints the newly generated temporary token in its JSON response, so handle that output as a credential.

Global `--timeout`, `--base-url`, and `--tiles-base-url` options go before the command. Override service URLs only for trusted services; authenticated requests send your token to that destination. JSON goes to stdout, errors to stderr; exit codes are 0 for success, 1 for SDK/input/output failures, and 2 for argument parsing errors. Tile downloads (`regrid tile ... --output FILE [--replace]`) check `--output` before requesting, write raw bytes to that file, and refuse to overwrite existing files unless `--replace` is given.

## Usage

Set `REGRID_TOKEN` in your environment, then:

```python
import os
from regrid import RegridClient

with RegridClient(os.environ["REGRID_TOKEN"]) as client:
    result = client.address("123 Main St, Dallas, TX", limit=1)
    for feature in result.get("parcels", {}).get("features", []):
        print(feature["properties"])
```

The constructor accepts `timeout=30`, an HTTPX `transport` for testing or custom transport behavior, `default_limit=5`, and `max_limit=1000`. Instances expose read-only `base_url`, `tiles_base_url`, and `timeout` properties alongside `request_count`.

Address searches default to one result; other supported parcel searches default to five. The client bounds requested limits by `max_limit`. A small limit controls returned records; it does **not** prove a unique or correct match. Resolve ambiguous addresses, boundary points, and stacked parcels in your application.

```python
with RegridClient(os.environ["REGRID_TOKEN"]) as client:
    nearby = client.point(lat=32.7767, lon=-96.7970, radius=10, limit=5)
    parcels = client.apn("0012340000", path="/us/tx/dallas", limit=5)
    filtered = client.query(
        {"geoid": {"eq": "48113"}},
        path="/us/tx/dallas",
        limit=5,
    )
    schema = client.schema()
```

Keep APNs as strings to preserve leading zeros and alphanumeric identifiers. Check the public schema for field names and the API documentation for supported operators.

## Typed responses with Pydantic v2

Use `TypedRegridClient` for typed response attributes and validation at the API boundary:

```python
import os
from regrid import TypedRegridClient
from regrid.models import CountResponse

with TypedRegridClient(os.environ["REGRID_TOKEN"]) as client:
    result = client.address("123 Main St, Dallas, TX", limit=1)
    if result.parcels is not None:
        for parcel in result.parcels.features:
            if parcel.properties is not None:
                print(parcel.properties.headline, parcel.properties.fields)

    data = result.to_dict()  # JSON-compatible dictionary; no second API request

    count = client.point(32.7767, -96.7970, return_count=True)
    if isinstance(count, CountResponse):
        print(count.count)

    # Explicit raw retrieval shares the same transport and lifetime:
    raw_usage = client.raw.usage()
```

Both clients have the same endpoint arguments, including `validate_query()` for offline query and paging checks without sending a request. `TypedRegridClient` returns parcel/count, usage, metadata, schema, typeahead, report, temporary-token, TileJSON, and UTFGrid models. Import model types from `regrid.models`. The original `RegridClient` and the CLI continue returning unchanged JSON dictionaries; adopting typed responses is opt-in.

Request validation uses strict types and endpoint-specific models with forbidden extra options. For example, `limit="5"`, `limit=True`, and `return_count="true"` are rejected rather than coerced. Numeric coordinate inputs must be finite and within range; APNs remain strings. Endpoint models are cached and reused. Invalid SDK inputs raise sanitized `ValueError` (some existing argument checks use `TypeError`).

Response models validate known fields strictly, accept unknown fields with `extra="allow"`, and retain arbitrary county attributes in `properties.fields`. `.to_dict()` preserves unknown fields, original aliases, and the distinction between omitted and explicitly null fields. Geometry types use a discriminated union; topology and polygon area remain server-validated. Matched addresses, enhanced ownership, buildings, zoning, typeahead properties, and county metadata have typed fields. Access their attributes directly or use `.to_dict()` for dictionaries. Direct schema maps remain lossless and expose validated field definitions through `.field_definitions`; enveloped responses retain `.schema_`.

Malformed known fields in typed responses raise `RegridDecodeError`. SDK request and typed-response validation errors omit input values and do not retain the underlying Pydantic validation exception. Non-finite upstream JSON numbers are rejected before model serialization can change them.

Account tokens are held as `SecretStr` internally. Temporary-token response models mask their token in representations and ordinary `model_dump()` output. Calling `ClientTokenResponse.to_dict()` or `token.get_secret_value()` explicitly reveals that temporary token; handle the result as a credential.

## Parcel field catalog

The versioned US catalog contains **169 fields** from the supplied July 9, 2026 schema. It records SQL datatypes, Standard/Premium tiers, documentation links, and known queryability and interpretation metadata. Field definitions are versioned `2026-07-09`; selected live metadata was reviewed on `2026-10-27`. Standardization distinguishes `yes`, `no`, `some`, and `not-applicable`. Unknown metadata is `None`, not a claim that a field is unavailable. Standard fields are also included in Premium. No coverage percentages or entitlements are inferred.

```python
from regrid.catalog import CATALOG_VERSION, PARCEL_FIELDS
from regrid.models import ParcelProperties

properties = ParcelProperties(fields={"parcelnumb": "00123", "ll_gisacre": 2.5})
assert properties.fields["parcelnumb"] == "00123"  # existing dictionary access
fields = properties.typed_fields  # explicit validation, no API call
if fields is not None:
    print(fields.parcelnumb, fields.ll_gisacre)
print(PARCEL_FIELDS["ll_gisacre"].coverage_column)  # ll_gisacre_pct
```

`ParcelFields` is also importable from `regrid.parcel_fields`. Accessing `.typed_fields` validates known US fields strictly and raises sanitized `RegridDecodeError` if they are malformed. Dates use ISO `YYYY-MM-DD`; timestamps require a time zone. Date, timestamp, and UUID strings retain their original spelling; identifiers retain leading zeros. Unknown attributes and missing/null distinctions survive `.to_dict()`. Ordinary typed responses and raw dictionaries remain usable without this additional validation. The US catalog is not a Canadian field schema.

Enable query checks explicitly with `client.query(filters, validate_fields=True)` or CLI `query --validate-fields`. Checks cover catalog queryability, documented operators, operand shapes/types, and incompatible ordering with pagination (`order` filters with `offset_id` paging or `--max-records` are rejected even without `validate_fields=True` / `--validate-fields`). `allow_unknown_fields=True` (CLI `--allow-unknown-fields`) permits fields with unknown queryability, including future additions; it does not bypass checks on known queryable fields or explicitly nonqueryable fields. Existing queries retain their prior behavior by default, including the four-field maximum. Catalog flags are local and never sent to Regrid.

The catalog is packaged with the library, so imports and validation never fetch metadata. After editing `src/regrid/data/parcel_fields.json`, run `.venv/bin/python scripts/generate_parcel_fields.py`; `--check` verifies reproducibility and is exercised by the test suite. See [field interpretation and follow-ups](docs/parcel-schema-guidance.md) for standardized alternatives, area/value distinctions, and coverage-report guidance.

## Methods

| Method | API resource |
| --- | --- |
| `point(lat=None, lon=None, geojson=None, country="us", method="GET", **options)` | `/parcels/point`; GeoJSON takes precedence over coordinates |
| `area(geojson, country="us", method="GET", **options)` | `/parcels/area` |
| `address(query, **options)` | `/parcels/address` |
| `apn(parcelnumb, **options)` | `/parcels/apn` |
| `owner(owner, **options)` | `/parcels/owner` |
| `query(fields, **options)` | `/parcels/query`; nested field → operator → value mapping |
| `validate_query(fields, *, paging=False, **options)` | Validates a query exactly as `query()` would, without sending a request; with `paging=True`, raises `QueryPagingError` (a `ValueError`) for filters that can't be used with `offset_id` paging |
| `parcel(ll_uuid, **options)` | `/parcels/{ll_uuid}` |
| `parcel_path(path, **options)` | `/parcels/path` |
| `typeahead(query)` | `/parcels/typeahead` |
| `client_token_typeahead(exp=None)` | `/client_token/typeahead`; expiration duration in seconds |
| `schema(name="parcel", **options)` | `/schemas/{name}`; public request without a token |
| `verse(country="us", **options)` | `/verse` |
| `usage(country="us", detailed=False, **options)` | `/usage` or `/usage/detailed` |
| `report(comment=None, path=None, ll_uuid=None, details=None)` | POST `/report`; creates an external data issue report |
| `tilejson(format="mvt")` | Tileserver metadata; `mvt` or `png` |
| `tile(z, x, y, format="mvt", retina=False)` | Tile bytes; retina applies to PNG |
| `grid(z, x, y, metadata=None)` | UTFGrid JSON from the raster TileJSON-advertised endpoint |

Use `country="ca"` on applicable parcel searches, metadata, and usage methods to select Canadian endpoints. Owner search and typeahead are US-only; detailed usage uses the global US-base route. Endpoint availability and options differ by country. Point and area support `method="POST"` for larger GeoJSON payloads; POST point requires GeoJSON. Additional keyword options become API request parameters; unsupported options raise `ValueError`.

The public schemas include `parcel`, `building`, `address`, `enhanced_ownership`, `zoning`, and `ca`. Parcel results usually appear in `result["parcels"]["features"]`; matched datasets can be separate top-level collections.

UTFGrid discovery makes one metadata request and one grid request. Pass previously retrieved raster TileJSON as `metadata` to reuse it. Grid URLs must remain on the configured HTTPS tileserver origin; metadata tokens are replaced with the client token.

## Cost and credentials

The SDK client performs no automatic retries or pagination. The CLI's opt-in `--max-records` pages only up to a precomputed request cap and reports every request on stderr. Parcel retrieval can incur charges per returned record. Applications should enforce call and record budgets, use geographic restrictions for broad searches, and handle cursors explicitly where supported. Usage responses describe consumption, not a documented remaining account balance.

Premium dataset defaults depend on API behavior and account access. Set supported flags such as `return_zoning`, `return_matched_buildings`, `return_matched_addresses`, and `return_enhanced_ownership` explicitly when controlling returned datasets. The SDK sends `return_parcels=True` by default on endpoints supporting that option because the supplied specification has conflicting defaults; pass `return_parcels=False` explicitly when needed. These controls do not guarantee billing outcomes. Count-request billing and retrieval behavior require verification before relying on them as cost controls.

Tokens are sent as query parameters. Keep them server-side and redact request URLs from logs. HTTPX info/debug logging can include URLs containing tokens; do not enable unredacted HTTP request logging. Regrid recommends separate Parcel API and Tileserver tokens; use a separate client instance with the appropriate token. Typeahead client tokens are intended for temporary, restricted browser access.

## Reference status

All 33 normalized operations and their parameters from the supplied US/Canada OpenAPI specification are implemented, along with TileJSON, raster/vector/retina tiles, and UTFGrid discovery. This is coverage of the supplied contract, not a claim to implement every subsequent addition to Regrid’s live API. Live service behavior, account entitlements, prices, and billing have not been verified. The source specification contains inconsistencies around defaults, geometry descriptions, examples, types, and nullability; raw responses remain available when upstream behavior differs from the opt-in response models.

See [REFERENCE.md](REFERENCE.md) for the supplied condensed reference, [Regrid API documentation](https://support.regrid.com/api), and the [documentation index](https://support.regrid.com/llms.txt) for upstream guidance.

## Errors and validation

Catch `RegridError` for SDK failures, `RegridHTTPError` for non-success HTTP status codes, `AuthenticationError` for missing credentials or HTTP 401/403, and `RegridDecodeError` for invalid JSON or failed typed-response validation. HTTP errors expose `status_code`; exception messages omit upstream bodies and request URLs. Transport failures are not retried. Redirects are not followed.

Invalid local arguments raise `ValueError` or `TypeError`. The client checks limits, coordinate ranges, supported options, and tile indices. Geometry topology, polygon area, and account permissions remain server-validated. Field/operator checks are available locally through opt-in US catalog validation; the server remains authoritative for current query support. Response dictionaries preserve unexpected and county-specific fields.

## Verification status

For Regrid Research 0.9.7 and SDK 0.5.0 (PR #33 and PR #34):
- **Tests:** `make check` passed **1639 tests** (2 skipped) with **97.69%** SDK/CLI coverage, `make e2e` passed **56**, `claude plugin validate --strict` passed and the 27 eval fixtures validated.
- **CI:** passed on Python 3.10, 3.12 and 3.13 and on Windows.
- **Packaging:** `uv build` verified a 28-file allowlisted sdist (`[tool.hatch.build.targets.sdist]` `only-include`) and wheel with 0 leaked local files; all 3 plugin archives rebuilt deterministically.
- **Live (authorized, 2026-11-24):** `make live` passed on SDK `0.5.0` (169 schema definitions, 0 type differences, geometry present, observed delta 1); direct Streamable HTTP `/mcp` against `https://support.regrid.com/mcp` with `x-regrid-token` verified `tools/list` (`tools.json` parity), `list-specs`, authenticated `GET /usage`, and `POST /parcels/area` with `return_parcels=true` (`limit=1`, returning `area` + 1 parcel feature with geometry and fields).
- **Map render check:** not re-rendered in a browser for `0.9.7` after `map.py` hardening (`NaN`/`Infinity` rejection, empty-path guards, `same_file_key` error handling); last plain-browser render check was `0.9.3`. See `plugins/regrid-research/evals/results/map-hosts-0.9.7.json`.
- **Not run:** the Claude Code, Claude apps and Cowork host UI/map checks, a fresh browser map render for `0.9.7`, typeahead (needs an Enterprise token), and model and Cowork acceptance evaluations.

For earlier release verification history and retained reports (`composability-0.5.0-report.json`, `authoring-0.4.0-report.json`, `final-report.json`, `forward-report.json`), see [changelog.md](changelog.md) and [plugins/regrid-research/evals/README.md](plugins/regrid-research/evals/README.md#historical-verification).

## Live smoke test

Set `REGRID_TOKEN` locally, then run `make live`. The default test address is `24 pennbrook dr haddonfield nj 08033`; optionally set `REGRID_LIVE_ADDRESS` to override it. An unset or blank override uses the default. `make live`, `make live-full`, and `make doctor` load your ignored `.env` through uv; exported environment values take precedence. For authenticated CLI calls use `uv run --env-file .env --no-sync regrid usage`; for SDK scripts use `uv run --env-file .env --no-sync python your_script.py`. Doctor checks configuration presence only, not token validity with Regrid. Loader errors are suppressed to avoid exposing credentials; failures return a generic diagnostic. Never paste tokens into reports or commit populated environment files.

Check local configuration, then run the explicitly authenticated smoke test:

```sh
make doctor
make live
# Optional: use another known complete US address
REGRID_LIVE_ADDRESS="your complete US property address" make live
```

The runner fetches the public parcel schema, records usage, looks up one address with `limit=1` and premium datasets disabled, validates the same response using Pydantic and opt-in parcel fields, then checks usage again. It makes at most four requests with no retries, pagination, or expanded searches. A parcel lookup may incur a charge. A single result is not proof of an exact address match, and usage can lag or include concurrent clients. Schema type drift is reported as a count. After the lookup it prints whether the parcel's geometry is present, null (no boundary on file) or absent (the satellite map would fail), without printing coordinates.

Output contains only status and aggregate counts, not credentials, addresses, owners, response bodies, or exception details. HTTP logging is disabled in the runner process. The underlying `regrid.live` module exits 2 for a missing or placeholder token before any network request, 1 for request/validation failures, and 0 on success. The Makefile recipe wraps any nonzero module or environment-loader result in a generic failure; do not rely on the module's exit code propagating through `make live`. If lookup or validation fails, final usage is still attempted. Tiles and premium datasets are not tested. This target runs separately from ordinary checks and local HTTPS E2E tests. `make live-full` (`regrid.live_full`) exercises every read-only endpoint, including POST search, paging, tiles and a deliberately invalid token, in about 26 requests with a hard cap of 30; it can incur a few parcel and tile charges, every search returns one or two records without premium datasets, and Enterprise typeahead runs only with `REGRID_LIVE_ENTERPRISE=1`. Its output has the same privacy rules as `make live` and adds PASS/FAIL/SKIP/NOTE lines with counts and status codes only, never addresses, coordinates, identifiers, owners or response bodies.

## Claude plugin

The [Regrid Research guide](plugins/regrid-research/README.md) covers separate
Cowork and Claude Code packages built from one canonical research skill:

- `dist/regrid-research-cowork-0.9.7.zip`: remote connector declaration and skills.
- `dist/regrid-research-claude-code-0.9.7.zip`: native HTTP MCP connection and skills.
- `dist/regrid-property-research-skill-0.9.7.zip`: standalone skill with references.

Build with `.venv/bin/python scripts/build_claude_plugins.py`. For Cowork,
configure `x-regrid-token` privately in the custom web connector's Request headers
settings. This is a limited beta and custom header names require approval.
Desktop Developer JSON and the local `.env` do not configure Cowork.

The skill verifies address/unit matches, honors finite-list budgets, distinguishes
missing facts from failed matches, and reuses retrieved responses. Its
[live tool reference](plugins/regrid-research/skills/property-research/references/mcp-tools.md)
records observed MCP schemas and a successful authenticated usage-only call.
[Offline evaluations](plugins/regrid-research/evals/README.md) test research decisions
using synthetic saved responses. Neither proves Cowork import or account-specific
header availability; those remain unverified. No credentials enter the packages.

Regrid Research 0.6.0 to 0.9.7 add:
- **Maps:** an interactive satellite parcel map (`scripts/map.py`, also `regrid map`) and the `/regrid-research:address-map` command for the address → data → map flow. Neighbouring outlines are opt-in.
- **Export:** CSV and GeoJSON (`map.py export`, also `regrid export`).
- **Field catalog:** `scripts/fields.py`, with `references/fields.json`.
- **County freshness:** pull dates via the CLI (`regrid freshness`).
- **Guidance:** premium datasets, address suggestions, refresh by Regrid path, count before pulling, and paging.
- **CLI path:** `references/cli.md` lets Claude Code run lookups through the `regrid` CLI under the same request budget.

Regrid Research 0.5.0 includes versioned handoffs, separate lookup/match statuses,
shared budgets, evidence reuse, and explicitly requested checkpoints. It adds
metadata-first discovery/baseline evaluations, direct resource links, qualified
MCP tool names, and actionable validation. See the
[composition guide](plugins/regrid-research/skills/property-research/references/composition.md)
and [checkpoint commands](plugins/regrid-research/skills/property-research/references/batch.md#optional-offline-helper).
The helper needs Python 3.10+ and no third-party packages.

To resume model acceptance testing after refreshing the separate Claude login:

```sh
claude auth login
python3 plugins/regrid-research/evals/run_discovery_claude.py --output /tmp/regrid-discovery-results
```

Use a new output directory for each run. The runner attempts 24 trials across
Haiku, Sonnet, and Opus, with a default USD 0.25 CLI budget per trial. It never
loads `.env` or enables Regrid tools. Completed trials still require independent
[rubric grading](plugins/regrid-research/evals/README.md#reproducible-claude-cli-runner);
they do not establish Cowork acceptance.

## License and project status

This community-maintained project is not an official Regrid SDK and is not
affiliated with or endorsed by Regrid. Project code is available under the
[MIT license](LICENSE). Regrid trademarks, service access, and parcel data remain
subject to their respective owners' terms; this license does not grant API or
data access. See [CONTRIBUTING.md](CONTRIBUTING.md) to participate.
