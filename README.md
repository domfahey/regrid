# Regrid SDK

A synchronous Python SDK and command-line client for the Regrid Parcel and Tileserver APIs, built on HTTPX and Pydantic v2. `RegridClient` keeps dictionary responses for compatibility; `TypedRegridClient` validates responses into models. Both validate request parameters strictly. Tile requests return bytes.

## Documentation

- [Architecture](architecture.md): components, request flow, validation boundaries, and extension points.
- [Contributor guidelines](AGENTS.md): repository layout, conventions, commands, and PR expectations.
- [Changelog](changelog.md): user-visible changes and release status.
- [API reference](REFERENCE.md): the supplied Regrid API documentation summary.
- [Operation coverage](docs/api-coverage.md): all 33 supplied OpenAPI operations and parameter profiles.
- [Response models](docs/model-coverage.md) and [UTFGrid](docs/utfgrid.md): typed fields and tileserver discovery.

## Installation

Requires Python 3.10 or later and [uv](https://docs.astral.sh/uv/). From this directory:

```sh
make install
cp .env.sample .env
# Edit .env locally with your Regrid token, then load it into your shell:
set -a
. ./.env
set +a
```

`.env` is not loaded automatically by the SDK or CLI. Keep real tokens only in your local environment or secret manager. `.env` and `.env.*` are ignored by Git; `.env.sample` contains only a placeholder. Never commit credentials, private keys, or populated environment files.

The editable installation provides `.venv/bin/regrid`. Activate `.venv` to use `regrid` directly, or run `uv run regrid`. Public schema commands do not require a token. This library resolves development dependencies locally; `uv.lock` is not tracked.

To install into another project:

```sh
uv add /absolute/path/to/regrid-sdk
```

## Development commands

| Command | Purpose |
| --- | --- |
| `make install` | Install the editable SDK, CLI, and development tools with uv |
| `make lint` | Run Ruff lint checks |
| `make format` | Format source and tests |
| `make format-check` | Verify formatting without editing files |
| `make typecheck` or `make type` | Run mypy on the SDK and CLI |
| `make test` | Run mocked tests and require at least 90% combined line and branch coverage |
| `make live` | Explicit bounded live Regrid smoke test; requires token; uses the default test address |
| `make e2e` | Run subprocess and real local HTTPS tests |
| `make check` | Run lint, format-check, typecheck, and the coverage-gated mocked suite |
| `uv build` | Build wheel and source archives into `dist/` |

Coverage includes every SDK and CLI module; XML output is written to ignored `coverage.xml`. E2E tests are separate from `make check`: they require `openssl` and permission to bind a localhost port, generate temporary TLS keys, and verify TLS using a temporary trusted certificate. They do not contact Regrid or incur API charges. Run `make check && make e2e` for the full suite. Override `PYTHON` if using a virtual environment other than `.venv`.

## Command line

```sh
.venv/bin/regrid --help
.venv/bin/regrid schema parcel
.venv/bin/regrid address "123 Main St, Dallas, TX" --options '{"limit":1,"path":"/us/tx/dallas"}'
.venv/bin/regrid apn "0012340000" --options '{"path":"/us/tx/dallas"}'
.venv/bin/regrid point --lat 32.7767 --lon -96.7970 --options '{"radius":10,"limit":5}'
.venv/bin/regrid query --fields '{"geoid":{"eq":"48113"}}' --options '{"limit":5}'
.venv/bin/regrid area --method POST --geojson @area.geojson --options '{"limit":5}'
.venv/bin/regrid usage --detailed
.venv/bin/regrid tilejson --format mvt
.venv/bin/regrid grid 15 8828 12121
.venv/bin/regrid tile 15 8828 12121 --format png --retina --output parcel.png
```

Every SDK method has a CLI command: `point`, `area`, `address`, `apn`, `owner`, `query`, `parcel`, `parcel-path`, `typeahead`, `client-token-typeahead`, `schema`, `verse`, `usage`, `report`, `tilejson`, `tile`, and `grid`. Use `<command> --help` for arguments. `python -m regrid` is equivalent to the installed command.

Use `--country ca` where Canadian endpoints are supported. `--options` accepts an object or `@file` containing JSON for supported SDK keyword parameters. `--fields` and `--geojson` also accept JSON or `@file`. Report details accept structured `--details` or plain `--details-text`; `report` submits an external data issue. The `client-token-typeahead` command intentionally prints the newly generated temporary token in its JSON response, so handle that output as a credential.

Global `--timeout`, `--base-url`, and `--tiles-base-url` options go before the command. Override service URLs only for trusted services; authenticated requests send your token to that destination. JSON goes to stdout, errors to stderr; exit codes are 0 for success, 1 for SDK/input/output failures, and 2 for argument parsing errors. Tile downloads require `--output` and write raw bytes to that file.

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

The constructor accepts `timeout=30`, an HTTPX `transport` for testing or custom transport behavior, `default_limit=5`, and `max_limit=1000`.

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

Both clients have the same endpoint arguments. `TypedRegridClient` returns parcel/count, usage, metadata, schema, typeahead, report, temporary-token, TileJSON, and UTFGrid models. Import model types from `regrid.models`. The original `RegridClient` and the CLI continue returning unchanged JSON dictionaries; adopting typed responses is opt-in.

Request validation uses strict types and endpoint-specific models with forbidden extra options. For example, `limit="5"`, `limit=True`, and `return_count="true"` are rejected rather than coerced. Numeric coordinate inputs must be finite and within range; APNs remain strings. Endpoint models are cached and reused. Invalid SDK inputs raise sanitized `ValueError` (some existing argument checks use `TypeError`).

Response models validate known fields strictly, accept unknown fields with `extra="allow"`, and retain arbitrary county attributes in `properties.fields`. `.to_dict()` preserves unknown fields, original aliases, and the distinction between omitted and explicitly null fields. Geometry types use a discriminated union; topology and polygon area remain server-validated. Matched addresses, enhanced ownership, buildings, zoning, typeahead properties, and county metadata have typed fields. Access their attributes directly or use `.to_dict()` for dictionaries. Direct schema maps remain lossless and expose validated field definitions through `.field_definitions`; enveloped responses retain `.schema_`.

Malformed known fields in typed responses raise `RegridDecodeError`. SDK request and typed-response validation errors omit input values and do not retain the underlying Pydantic validation exception. Non-finite upstream JSON numbers are rejected before model serialization can change them.

Account tokens are held as `SecretStr` internally. Temporary-token response models mask their token in representations and ordinary `model_dump()` output. Calling `ClientTokenResponse.to_dict()` or `token.get_secret_value()` explicitly reveals that temporary token; handle the result as a credential.

## Parcel field catalog

The versioned US catalog contains **169 fields** from the supplied July 9, 2026 schema. It records SQL datatypes, Standard/Premium tiers, documentation links, and known queryability and interpretation metadata. Unknown metadata is `None`, not a claim that a field is unavailable. Standard fields are also included in Premium. No coverage percentages or entitlements are inferred.

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

Enable query checks explicitly with `client.query(filters, validate_fields=True)` or CLI `query --validate-fields`. Checks cover catalog queryability, documented operators, operand shapes/types, and incompatible ordering with pagination. `allow_unknown_fields=True` (CLI `--allow-unknown-fields`) permits fields with unknown queryability, including future additions; it does not bypass checks on known queryable fields or explicitly nonqueryable fields. Existing queries retain their prior behavior by default, including the four-field maximum. Catalog flags are local and never sent to Regrid.

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

The client performs no automatic retries or pagination. Parcel retrieval can incur charges per returned record. Applications should enforce call and record budgets, use geographic restrictions for broad searches, and handle cursors explicitly where supported. Usage responses describe consumption, not a documented remaining account balance.

Premium dataset defaults depend on API behavior and account access. Set supported flags such as `return_zoning`, `return_matched_buildings`, `return_matched_addresses`, and `return_enhanced_ownership` explicitly when controlling returned datasets. The SDK sends `return_parcels=True` by default on endpoints supporting that option because the supplied specification has conflicting defaults; pass `return_parcels=False` explicitly when needed. These controls do not guarantee billing outcomes. Count-request billing and retrieval behavior require verification before relying on them as cost controls.

Tokens are sent as query parameters. Keep them server-side and redact request URLs from logs. HTTPX info/debug logging can include URLs containing tokens; do not enable unredacted HTTP request logging. Regrid recommends separate Parcel API and Tileserver tokens; use a separate client instance with the appropriate token. Typeahead client tokens are intended for temporary, restricted browser access.

## Reference status

All 33 normalized operations and their parameters from the supplied US/Canada OpenAPI specification are implemented, along with TileJSON, raster/vector/retina tiles, and UTFGrid discovery. This is coverage of the supplied contract, not a claim to implement every subsequent addition to Regrid’s live API. Live service behavior, account entitlements, prices, and billing have not been verified. The source specification contains inconsistencies around defaults, geometry descriptions, examples, types, and nullability; raw responses remain available when upstream behavior differs from the opt-in response models.

See [REFERENCE.md](REFERENCE.md) for the supplied condensed reference, [Regrid API documentation](https://support.regrid.com/api), and the [documentation index](https://support.regrid.com/llms.txt) for upstream guidance.

## Errors and validation

Catch `RegridError` for SDK failures, `RegridHTTPError` for non-success HTTP status codes, `AuthenticationError` for missing credentials or HTTP 401/403, and `RegridDecodeError` for invalid JSON or failed typed-response validation. HTTP errors expose `status_code`; exception messages omit upstream bodies and request URLs. Transport failures are not retried. Redirects are not followed.

Invalid local arguments raise `ValueError` or `TypeError`. The client checks limits, coordinate ranges, supported options, and tile indices. Geometry topology, polygon area, valid server-side query fields/operators, and account permissions remain server-validated. Response dictionaries preserve unexpected and county-specific fields.

## Verification status

The mocked suite has 278 passing tests and 99.23% combined line and branch coverage, including 100% CLI and typed-client coverage. Validation was run on Python 3.12 with Pydantic 2.12.5. Lint, formatting, and type checks pass. Four HTTPS E2E cases are implemented but could not execute in the authoring sandbox because localhost socket binding is denied. No live Regrid account or billing tests have been performed.

A targeted test-quality audit replaced route-only, truthiness, and configuration-inspection assertions with full request contracts, exact binary output, timeout forwarding, explicit false/zero preservation, and typed attribute checks. Seven controlled mutations that survived the previous assertions were caught by their replacements; this was a focused regression check, not a whole-project mutation score.

## Live smoke test

Set `REGRID_TOKEN` locally, then run `make live`. The default test address is `24 pennbrook dr haddonfield nj 08033`; optionally set `REGRID_LIVE_ADDRESS` to override it. An unset or blank override uses the default. You may load your ignored `.env` using the installation instructions above; the runner does not load it automatically. Never paste tokens into reports or commit populated environment files.

The runner fetches the public parcel schema, records usage, looks up one address with `limit=1` and premium datasets disabled, validates the same response using Pydantic and opt-in parcel fields, then checks usage again. It makes at most four requests with no retries, pagination, or expanded searches. A parcel lookup may incur a charge. A single result is not proof of an exact address match, and usage can lag or include concurrent clients. Schema type drift is reported as a count.

Output contains only status and aggregate counts, not credentials, addresses, owners, response bodies, or exception details. HTTP logging is disabled in the runner process. A missing or placeholder token exits with status 2 before any network request; failed requests or validation exit with status 1; success exits with status 0. If lookup or validation fails, final usage is still attempted. Tiles and premium datasets are not tested. This target runs separately from ordinary checks and local HTTPS E2E tests.
